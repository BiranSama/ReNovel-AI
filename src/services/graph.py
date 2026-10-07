"""知识图谱构建：从已保存的章节抽取人物 / 物品等实体之间的关系。

- 以库里的章节为单位（不再按“第”字切分全文），章节位置即关系的出现章节
- 长章节分段抽取，整章都会被分析
- 每章记录内容指纹，内容没变的章节下次不再重复调用模型（真正的增量更新）
- 只从已保存的正文抽取：未采纳的改写草稿不会进入图谱
"""
import asyncio
import hashlib
import json
import re
import shutil
from typing import Callable, Optional

from src import paths
from src.llm import LLMError
from src.llm.prompts import join_sections, section

PIECE_CHARS = 3000
MIN_CHAPTER_CHARS = 50
EXTRACTOR_SYSTEM = "You are a data extractor. Output ONLY valid JSON list."
JSON_FORMAT = ('[\n  {"source": "实体A", "relation": "关系", "target": "实体B", '
               '"desc": "关系描述", "is_reveal": false}\n]\n'
               'is_reveal 表示这是一条此前隐藏、在本段才揭示的关系（伏笔）。')


def clone_graph(old_project_id: str, new_project_id: str, chapter_map: Optional[dict] = None) -> None:
    """复制项目时一并复制图谱文件（没有图谱则跳过）。

    副本里的章节 id 是新生成的：按 chapter_map（原章节 id → 副本章节 id）改写内容指纹与关系来源，
    否则副本更新图谱时会把没改过的章节当成新章节重新分析。
    """
    source = paths.graph_file(old_project_id)
    if not source.exists():
        return
    target = paths.graph_file(new_project_id)
    if not chapter_map:
        shutil.copyfile(source, target)
        return
    data = json.loads(source.read_text(encoding="utf-8"))
    graph_attrs = data.get("graph", {})
    graph_attrs["extracted"] = {chapter_map.get(k, k): v for k, v in graph_attrs.get("extracted", {}).items()}
    for link in data.get("links", []):
        if link.get("sources"):
            link["sources"] = {chapter_map.get(k, k): v for k, v in link["sources"].items()}
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class GraphParseError(ValueError):
    """模型返回的内容不是有效的关系列表。"""


def fingerprint(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def pieces(text: str, size: int = PIECE_CHARS) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


def parse_triples(raw: str) -> list[dict]:
    """解析模型返回的关系列表。返回 [] 表示确实没有关系；格式无效时抛出 GraphParseError。"""
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise GraphParseError("模型没有返回 JSON 列表")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as error:
        raise GraphParseError(f"JSON 无法解析：{error}") from error
    return [t for t in data if isinstance(t, dict) and all(t.get(k) for k in ("source", "relation", "target"))]


class GraphService:
    def __init__(self, llm, settings, projects):
        self.llm = llm
        self.settings = settings
        self.projects = projects
        self._locks: dict[str, asyncio.Lock] = {}

    async def extract(self, engine, text: str, chapter_index: int, chapter_id: Optional[str] = None) -> int:
        """从一段文本抽取关系写入图谱，返回新增关系数。

        模型调用失败时抛出 LLMError；返回内容格式无效时抛出 GraphParseError。
        """
        known = "、".join(map(str, engine.entity_names()))
        prompt = join_sections(
            "知识图谱提取。请提取【实体-关系-实体】三元组。",
            section("已知实体（同一实体请沿用这些名称）", known),
            section("JSON格式", JSON_FORMAT),
            section("待分析文本", text),
        )
        messages = [{"role": "system", "content": EXTRACTOR_SYSTEM}, {"role": "user", "content": prompt}]
        raw = await self.llm.complete(self.settings.resolve_role("graph"), messages)
        added = 0
        for t in parse_triples(raw):
            added += engine.add_relation(
                t["source"], t["target"], t["relation"], chapter_id=chapter_index,
                reveal_chapter=chapter_index, is_secret=bool(t.get("is_reveal")), desc=t.get("desc", ""),
                from_chapter=chapter_id,
            )
        return added

    async def update(
        self,
        engine,
        project_id: str,
        on_progress: Optional[Callable[[str, float], None]] = None,
        chapter_ids: Optional[set] = None,
    ) -> int:
        """分析内容有变化的章节（可限定 chapter_ids），返回新增关系数。出错时已完成的部分会保存。

        章节内容变了：先撤销这一章以前抽取的关系再重新抽取，删掉或改写的情节不会继续作为事实留在图谱里。
        某段的返回内容无效时，这一章不记录指纹，下次更新会重试。
        """
        async with self._lock(project_id):  # 多个标签页同时更新同一项目时依次进行，后者只处理仍有变化的章节
            return await self._update(engine, project_id, on_progress, chapter_ids)

    def _lock(self, project_id: str) -> asyncio.Lock:
        return self._locks.setdefault(project_id, asyncio.Lock())

    async def _update(self, engine, project_id, on_progress, chapter_ids) -> int:
        chapters = await self.projects.get_chapters(project_id)
        added = 0
        try:
            for position, chapter in enumerate(chapters, start=1):
                if chapter_ids is not None and chapter["id"] not in chapter_ids:
                    continue
                text = await self.projects.get_chapter_content(chapter["id"]) or ""
                mark = fingerprint(text)
                if engine.chapter_fingerprint(chapter["id"]) == mark:
                    continue
                engine.remove_chapter(chapter["id"])
                parsed_all = True
                if len(text) >= MIN_CHAPTER_CHARS:  # 太短的章节（如很短的序章、被清空的章节）不调用模型
                    if on_progress:
                        on_progress(f"图谱：分析 {chapter['title']}（{position}/{len(chapters)}）", position / len(chapters))
                    for piece in pieces(text):
                        try:
                            added += await self.extract(engine, piece, position, chapter["id"])
                        except GraphParseError:
                            parsed_all = False
                if parsed_all:
                    engine.mark_extracted(chapter["id"], mark)
                engine.save_graph()
        except LLMError:
            engine.save_graph()
            raise
        return added
