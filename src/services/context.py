"""为改写 / 审校 / 分析组装参考资料：章节记忆、向量记忆、角色档案、知识图谱。

视角（view）：
    reader  只用当前章节之前的内容（前情提要、前文片段、截至上一章的角色状态、已揭示的关系），
            给 Writer 和「本章」聊天，避免提前泄露后文
    author  用全书内容（全部片段、完整的状态变化、前文事件、含伏笔的关系），给 Reviewer 和 Analyzer
            检查 OOC、时间线和伏笔
"""
from typing import Callable, Iterable, Optional, Protocol

from src.llm.prompts import join_sections, section
from src.services.characters import CharacterProfile, build_profiles, mentioned

QUERY_CHARS = 500     # 检索时只取开头一段：嵌入模型本身也会截断长文本
RECAP_CHAPTERS = 3    # 前情提要取最近几章的摘要
MAX_EVENTS = 8        # 前文事件最多列几条
MAX_PROFILES = 6      # 角色档案最多列几个
MAX_STATUSES = 3      # 读者视角每个角色列最近几条状态变化


class MemorySearch(Protocol):
    async def asearch(self, query: str, project_id: str, n_results: int = 5,
                      chapter_ids: Optional[Iterable[str]] = None) -> list[str]: ...


class RelationGraph(Protocol):
    def context_for_text(self, text: str, current_chapter: int, mode: str = "reader") -> str: ...


class ContextBuilder:
    def __init__(
        self,
        memory: Optional[MemorySearch],
        graph_provider: Callable[[Optional[str]], Optional[RelationGraph]] = lambda project_id: None,
        n_results: int = 5,
        projects=None,       # ProjectManager：按章节顺序区分前文与后文
        chapter_store=None,  # ChapterMemoryStore：章节记忆与角色档案的修订
    ):
        self.memory = memory
        self.graph_provider = graph_provider
        self.n_results = n_results
        self.projects = projects
        self.chapter_store = chapter_store

    async def gather(self, project_id: Optional[str], text: str, chapter_index: int, view: str = "reader") -> str:
        """chapter_index 是当前章节的序号（从 1 开始）；0 表示不在任何章节里，读者视角下没有前文。"""
        chapters, memories, overrides = await self._load(project_id)
        earlier = chapters[:max(chapter_index - 1, 0)] if chapters is not None else None
        reader = view == "reader"
        if reader:  # 别名、性格、经历都只从前面章节的记忆汇总；用户手动填写的修订保留
            visible = {c["id"]: memories[c["id"]] for c in earlier or [] if c["id"] in memories}
            profiles = build_profiles(earlier or [], visible, overrides)
        else:
            profiles = build_profiles(chapters or [], memories, overrides)
        involved = mentioned(profiles, text)[:MAX_PROFILES]
        return join_sections(
            section("前情提要", self._recap(earlier, memories)) if reader else "",
            section("相关记忆", await self._memories(project_id, text, earlier if reader else None)),
            section("角色档案", self._profiles(involved, chapter_index if reader else None)),
            section("前文事件", self._events(earlier, memories, involved)) if not reader else "",
            section("人物关系", self._relations(project_id, text, chapter_index, view)),
        )

    async def _load(self, project_id):
        if not project_id or not self.projects:
            return None, {}, {}
        chapters = await self.projects.get_chapters(project_id)
        if not self.chapter_store:
            return chapters, {}, {}
        return chapters, await self.chapter_store.for_project(project_id), await self.chapter_store.overrides(project_id)

    async def _memories(self, project_id: Optional[str], text: str, earlier: Optional[list[dict]]) -> str:
        if not project_id or not self.memory or not text.strip():
            return ""
        kwargs = {}
        if earlier is not None:  # 读者视角：只在前面的章节里找
            if not earlier:
                return ""
            kwargs["chapter_ids"] = [c["id"] for c in earlier]
        # 多取一条：检索结果里通常有待改写的这段原文本身，需要排除
        docs = await self.memory.asearch(text[:QUERY_CHARS], project_id, self.n_results + 1, **kwargs)
        own = text.strip()
        docs = [d for d in docs if d.strip() and d.strip() not in own][: self.n_results]
        return "\n".join(f"- {d}" for d in docs)

    @staticmethod
    def _recap(earlier: Optional[list[dict]], memories: dict) -> str:
        lines = []
        for chapter in (earlier or [])[-RECAP_CHAPTERS:]:
            memory = memories.get(chapter["id"])
            if memory and memory.summary:
                lines.append(f"- {chapter['title']}：{memory.summary}")
        return "\n".join(lines)

    @staticmethod
    def _profiles(profiles: list[CharacterProfile], before_chapter: Optional[int]) -> str:
        """before_chapter 不为空时（读者视角）只列这一章之前的状态变化，且只列最近几条。"""
        blocks = []
        for profile in profiles:
            parts = [profile.name + (f"（又名：{'、'.join(profile.aliases)}）" if profile.aliases else "")]
            if profile.traits_text():
                parts.append(f"性格：{profile.traits_text()}")
            if profile.notes:
                parts.append(f"设定：{profile.notes}")
            statuses = profile.statuses_before(before_chapter)
            if before_chapter is not None:
                statuses = statuses[-MAX_STATUSES:]
            if statuses:
                parts.append("经历：" + "；".join(f"{s.chapter_title} {s.status}" for s in statuses))
            if len(parts) > 1 or profile.aliases:  # 只有名字、没有任何资料的角色不列
                blocks.append("- " + "；".join(parts))
        return "\n".join(blocks)

    @staticmethod
    def _events(earlier: Optional[list[dict]], memories: dict, profiles: list[CharacterProfile]) -> str:
        """前面章节里与本段角色有关的事件，越近越优先。"""
        names = [n for p in profiles for n in p.names]
        picked: list[str] = []
        for chapter in reversed(earlier or []):
            memory = memories.get(chapter["id"])
            events = memory.events if memory else []
            picked[:0] = [f"- {chapter['title']}：{e}" for e in events if any(n in e for n in names)]
            if len(picked) >= MAX_EVENTS:
                break
        return "\n".join(picked[-MAX_EVENTS:])

    def _relations(self, project_id: Optional[str], text: str, chapter_index: int, view: str) -> str:
        graph = self.graph_provider(project_id)
        return graph.context_for_text(text, chapter_index, view) if graph else ""
