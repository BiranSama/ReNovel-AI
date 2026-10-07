"""知识图谱构建：从已保存的章节抽取人物 / 物品等实体之间的关系。

- 以库里的章节为单位（不再按“第”字切分全文），章节位置即关系的出现章节
- 长章节分段抽取，整章都会被分析
- 每章记录内容指纹，内容没变的章节下次不再重复调用模型（真正的增量更新）
- 只从已保存的正文抽取：未采纳的改写草稿不会进入图谱
"""
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


def clone_graph(old_project_id: str, new_project_id: str) -> None:
    """复制项目时一并复制图谱文件（没有图谱则跳过）。"""
    source = paths.graph_file(old_project_id)
    if source.exists():
        shutil.copyfile(source, paths.graph_file(new_project_id))


def fingerprint(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def pieces(text: str, size: int = PIECE_CHARS) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


def parse_triples(raw: str) -> list[dict]:
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [t for t in data if isinstance(t, dict) and all(t.get(k) for k in ("source", "relation", "target"))]


class GraphService:
    def __init__(self, llm, settings, projects):
        self.llm = llm
        self.settings = settings
        self.projects = projects

    async def extract(self, engine, text: str, chapter_index: int) -> int:
        """从一段文本抽取关系写入图谱，返回新增关系数。模型调用失败时抛出 LLMError。"""
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
            )
        return added

    async def update(
        self,
        engine,
        project_id: str,
        on_progress: Optional[Callable[[str, float], None]] = None,
        chapter_ids: Optional[set] = None,
    ) -> int:
        """分析内容有变化的章节（可限定 chapter_ids），返回新增关系数。出错时已完成的部分会保存。"""
        chapters = await self.projects.get_chapters(project_id)
        added = 0
        try:
            for position, chapter in enumerate(chapters, start=1):
                if chapter_ids is not None and chapter["id"] not in chapter_ids:
                    continue
                text = await self.projects.get_chapter_content(chapter["id"])
                mark = fingerprint(text)
                if len(text) < MIN_CHAPTER_CHARS or engine.chapter_fingerprint(chapter["id"]) == mark:
                    continue
                if on_progress:
                    on_progress(f"图谱：分析 {chapter['title']}（{position}/{len(chapters)}）", position / len(chapters))
                for piece in pieces(text):
                    added += await self.extract(engine, piece, position)
                engine.mark_extracted(chapter["id"], mark)
                engine.save_graph()
        except LLMError:
            engine.save_graph()
            raise
        return added
