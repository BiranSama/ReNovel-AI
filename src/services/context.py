"""为改写 / 审校 / 分析组装参考资料：向量记忆 + 知识图谱。

视角（view）：
    reader  只含截至当前章节已揭示的关系，给 Writer，避免提前泄露伏笔
    author  含全部关系并标注伏笔，给 Reviewer 和 Analyzer
"""
from typing import Callable, Optional, Protocol

from src.llm.prompts import join_sections, section

QUERY_CHARS = 500  # 检索时只取开头一段：嵌入模型本身也会截断长文本


class MemorySearch(Protocol):
    async def asearch(self, query: str, project_id: str, n_results: int = 5) -> list[str]: ...


class RelationGraph(Protocol):
    def context_for_text(self, text: str, current_chapter: int, mode: str = "reader") -> str: ...


class ContextBuilder:
    def __init__(
        self,
        memory: Optional[MemorySearch],
        graph_provider: Callable[[Optional[str]], Optional[RelationGraph]] = lambda project_id: None,
        n_results: int = 5,
    ):
        self.memory = memory
        self.graph_provider = graph_provider
        self.n_results = n_results

    async def gather(self, project_id: Optional[str], text: str, chapter_index: int, view: str = "reader") -> str:
        return join_sections(
            section("相关记忆", await self._memories(project_id, text)),
            section("人物关系", self._relations(project_id, text, chapter_index, view)),
        )

    async def _memories(self, project_id: Optional[str], text: str) -> str:
        if not project_id or not self.memory or not text.strip():
            return ""
        # 多取一条：检索结果里通常有待改写的这段原文本身，需要排除
        docs = await self.memory.asearch(text[:QUERY_CHARS], project_id, self.n_results + 1)
        own = text.strip()
        docs = [d for d in docs if d.strip() and d.strip() not in own][: self.n_results]
        return "\n".join(f"- {d}" for d in docs)

    def _relations(self, project_id: Optional[str], text: str, chapter_index: int, view: str) -> str:
        graph = self.graph_provider(project_id)
        return graph.context_for_text(text, chapter_index, view) if graph else ""
