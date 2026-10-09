"""章节记忆：从已保存的正文为每章整理摘要、出场角色和关键事件。

- 只读已保存的正文（编辑器里未保存的草稿不算）
- 记录生成时的正文指纹，内容没变的章节不再调用模型
- 很短的章节（如只有一句话的序章、被清空的章节）不调用模型，记为空记忆
- 某章的返回内容无效时不记录，下次更新重试
"""
import asyncio
from typing import Callable, Optional

from src.core.chapter_memory_store import CharacterNote, ChapterMemory, ChapterMemoryStore
from src.llm.prompts import assemble_system_prompt, join_sections, parse_json_object, section
from src.services.graph import fingerprint
from src.services.refine import excerpt

MIN_CHAPTER_CHARS = 50
CHAPTER_EXCERPT_CHARS = 12000  # 超长章节取开头和结尾
MAX_KNOWN_CHARACTERS = 60
INSTRUCTION = ('请整理这一章的记忆，只输出 JSON：{"summary": "150 字以内的情节摘要", '
               '"characters": ["出场角色，沿用已知角色的名字"], "events": ["关键事件：谁做了什么、结果如何，3 到 6 条"], '
               '"character_notes": [{"name": "角色名", "aliases": ["本章出现的其他称呼"], '
               '"traits": "本章体现的性格，没有则留空", "status": "本章结束时的状态变化（如受伤、离开、身份暴露），没有则留空"}], '
               '"hooks": ["本章埋下、尚未揭晓的悬念或伏笔，没有则为空列表"]}')


class MemoryParseError(ValueError):
    """模型返回的内容不是有效的章节记忆。"""


def parse_memory(chapter_id: str, raw: str) -> ChapterMemory:
    data = parse_json_object(raw)
    if data is None or not isinstance(data.get("summary"), str) or not data["summary"].strip():
        # 正文足够长的章节一定能写出摘要；空对象或空摘要当作失败，下次重试，而不是记成“已整理”
        raise MemoryParseError("模型没有返回有效的章节记忆（缺少摘要）")

    def strings(key):
        value = data.get(key) or []
        return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []

    notes = []
    for item in data.get("character_notes") or []:
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            continue
        aliases = item.get("aliases") if isinstance(item.get("aliases"), list) else []
        name = str(item["name"]).strip()
        notes.append(CharacterNote(name, [str(a).strip() for a in aliases if str(a).strip() and str(a).strip() != name],
                                   str(item.get("traits") or "").strip(), str(item.get("status") or "").strip()))
    return ChapterMemory(chapter_id, data.get("summary", "").strip(), strings("characters"), strings("events"),
                         notes=notes, hooks=strings("hooks"))


class ChapterMemoryService:
    def __init__(self, llm, settings, projects, store: ChapterMemoryStore):
        self.llm = llm
        self.settings = settings
        self.projects = projects  # ProjectManager
        self.store = store
        self._locks: dict[str, asyncio.Lock] = {}

    async def summarize(self, chapter: dict, text: str, known_characters: list[str]) -> ChapterMemory:
        """整理一章的记忆。模型调用失败抛 LLMError，返回内容无效抛 MemoryParseError。"""
        prompt = join_sections(
            section("已知角色", "、".join(known_characters[:MAX_KNOWN_CHARACTERS])),
            section("章节标题", chapter.get("title", "")),
            section("正文", excerpt(text, CHAPTER_EXCERPT_CHARS)),
            INSTRUCTION,
        )
        system = assemble_system_prompt(self.settings.get_role_config("memory"), self.settings.is_nsfw_enabled())
        raw = await self.llm.complete(self.settings.resolve_role("memory"),
                                      [{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        return parse_memory(chapter["id"], raw)

    async def update(
        self,
        project_id: str,
        on_progress: Optional[Callable[[str, float], None]] = None,
        chapter_ids: Optional[set] = None,
    ) -> int:
        """整理内容有变化的章节（可限定 chapter_ids），返回整理了几章。模型调用失败时抛 LLMError，已完成的章节已保存。

        同一项目的整理按项目加锁依次进行（多个标签页同时保存时），后一个只处理仍有变化的章节。
        """
        async with self._locks.setdefault(project_id, asyncio.Lock()):
            return await self._update(project_id, on_progress, chapter_ids)

    async def _update(self, project_id, on_progress, chapter_ids) -> int:
        chapters = await self.projects.get_chapters(project_id)
        memories = await self.store.for_project(project_id)
        updated = 0
        for position, chapter in enumerate(chapters, start=1):
            if chapter_ids is not None and chapter["id"] not in chapter_ids:
                continue
            text = await self.projects.get_chapter_content(chapter["id"]) or ""
            mark = fingerprint(text)
            old = memories.get(chapter["id"])
            if old and old.fingerprint == mark:
                continue
            if old:  # 正文改过：旧记忆说的是改之前的内容，先删掉，整理失败时改写和续写也不会再用它
                await self.store.delete(chapter["id"])
                del memories[chapter["id"]]
            if len(text.strip()) < MIN_CHAPTER_CHARS:
                memory = ChapterMemory(chapter["id"])
            else:
                if on_progress:
                    on_progress(f"记忆：整理 {chapter['title']}（{position}/{len(chapters)}）", position / len(chapters))
                known = known_characters(memories, chapters[:position - 1])
                try:
                    memory = await self.summarize(chapter, text, known)
                except MemoryParseError:
                    continue  # 不记录指纹，下次重试
            memory.fingerprint = mark
            await self.store.save(project_id, memory)
            memories[chapter["id"]] = memory
            updated += 1
        return updated

    async def chapter_memories(self, project_id: str) -> list[tuple[dict, Optional[ChapterMemory]]]:
        """按章节顺序列出各章及其记忆（没有整理过的为 None）。"""
        memories = await self.store.for_project(project_id)
        return [(c, memories.get(c["id"])) for c in await self.projects.get_chapters(project_id)]


def known_characters(memories: dict[str, ChapterMemory], earlier_chapters: list[dict]) -> list[str]:
    """前面各章出现过的角色，出场越多越靠前。"""
    counts: dict[str, int] = {}
    for chapter in earlier_chapters:
        for name in getattr(memories.get(chapter["id"]), "characters", []):
            counts[name] = counts.get(name, 0) + 1
    return sorted(counts, key=lambda name: -counts[name])

