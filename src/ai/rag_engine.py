"""向量记忆：章节正文按段落存进向量库，改写、审校、聊天时按语义检索相关的前文。

记忆只是已保存正文的索引，随时可以从项目数据库重建；旧版本的 ChromaDB 数据就是这样迁移的。
检索失败（如本地模型下载失败、API 出错）时返回空结果并记下原因，不影响改写本身。
"""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, Optional

from src import paths
from src.ai.embeddings import Embedder, create_embedder
from src.ai.vector_store import VectorStore
from src.utils.logger import ConsoleLogger as Log

MIN_LINE_CHARS = 6  # 太短的行（如“嗯。”）检索价值不大
LEGACY_MIGRATED = "legacy_chroma_migrated"


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").split("\n") if len(line.strip()) >= MIN_LINE_CHARS]


class RAGEngine:
    def __init__(self, embedding_config: Optional[Callable[[], dict]] = None,
                 embedder: Optional[Embedder] = None, db_path=None):
        """embedding_config 返回设置里的 embedding 配置（改了设置会自动换模型）；embedder 直接指定（测试用）。"""
        self.store = VectorStore(db_path or paths.memory_db())
        self._config = embedding_config or (lambda: {})
        self._fixed = embedder
        self._embedder, self._embedder_key = None, None
        self.last_error = ""
        # 嵌入计算和数据库读写都是阻塞调用（首次还要下载模型）：放到一个专用线程里依次执行，
        # 界面的事件循环不会被卡住；单线程也避免多个标签页同时写入
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag")
        self._rebuilding: dict[str, asyncio.Event] = {}  # 正在从旧数据重建记忆的项目

    def embedder(self) -> Embedder:
        if self._fixed:
            return self._fixed
        config = self._config() or {}
        key = json.dumps(config, sort_keys=True, ensure_ascii=False)
        if key != self._embedder_key:
            self._embedder, self._embedder_key = create_embedder(config), key
        return self._embedder

    # --- 异步接口：界面和服务都用这些 ---
    async def _in_thread(self, fn, *args):
        return await asyncio.get_running_loop().run_in_executor(self._executor, fn, *args)

    async def asearch(self, query: str, project_id: str, n_results=5, chapter_ids=None) -> list[str]:
        await self._wait_rebuilt(project_id)
        return await self._in_thread(self.search, query, project_id, n_results, chapter_ids)

    async def aindex_chapter(self, project_id: str, chapter_id: str, text: str):
        return await self._in_thread(self.index_chapter, project_id, chapter_id, text)

    async def aclone_project_memory(self, old_pid: str, new_pid: str, chapter_map: Optional[dict] = None):
        await self._wait_rebuilt(old_pid)  # 否则副本只复制到已经重建的部分，之后也不会补上
        return await self._in_thread(self.clone_project_memory, old_pid, new_pid, chapter_map)

    # --- 从旧数据重建期间：检索和复制等这个项目重建完（重建只在升级后第一次启动时进行一次）---
    def begin_rebuild(self, project_ids: Iterable[str]) -> None:
        for project_id in project_ids:
            self._rebuilding[project_id] = asyncio.Event()

    def finish_rebuild(self, project_id: str) -> None:
        event = self._rebuilding.pop(project_id, None)
        if event:
            event.set()

    async def _wait_rebuilt(self, project_id: str) -> None:
        event = self._rebuilding.get(project_id)
        if event:
            await event.wait()

    # --- 同步实现 ---
    def index_chapter(self, project_id: str, chapter_id: str, text: str) -> None:
        """用章节的最新内容替换它的记忆。向量生成失败时先只存原文，检索时再补。"""
        lines = split_lines(text)
        embedder = self.embedder()
        vectors = None
        if lines:
            try:
                vectors = embedder.embed(lines)
            except Exception as error:
                self._fail(error)
        self.store.replace_chapter(project_id, chapter_id, lines, embedder.name, vectors)

    def search(self, query: str, project_id: str, n_results=5, chapter_ids: Optional[Iterable[str]] = None) -> list[str]:
        """按语义检索本项目的记忆片段；chapter_ids 不为空时只在这些章节里找。失败时返回空列表。"""
        if not project_id or not (query or "").strip():
            return []
        try:
            embedder = self.embedder()
            self._refresh(project_id, embedder)
            query_vector = embedder.embed([query])[0]
        except Exception as error:
            self._fail(error)
            return []
        self.last_error = ""
        return self.store.search(project_id, embedder.name, query_vector, n_results, chapter_ids)

    def clone_project_memory(self, old_pid: str, new_pid: str, chapter_map: Optional[dict] = None) -> None:
        """复制项目时一并复制记忆（直接复用向量）；chapter_map 把原章节 id 换成副本的章节 id。"""
        count = self.store.clone_project(old_pid, new_pid, chapter_map)
        Log.system(f"[RAG] 记忆复制完成：{count} 条")

    def delete_project_memory(self, project_id: str) -> None:
        self.store.delete_project(project_id)

    def _refresh(self, project_id: str, embedder: Embedder) -> None:
        """补上缺失或由其他模型生成的向量（换了模型、或之前生成失败）。"""
        while batch := self.store.stale(project_id, embedder.name):
            ids, texts = zip(*batch)
            self.store.set_vectors(project_id, list(ids), embedder.name, embedder.embed(list(texts)))

    def _fail(self, error: Exception) -> None:
        self.last_error = str(error)
        Log.system(f"[RAG] 向量生成失败：{error}")

    # --- 旧版本 ChromaDB 数据迁移 ---
    def needs_migration(self) -> bool:
        return (paths.vectordb_dir() / "chroma.sqlite3").exists() and not self.store.get_meta(LEGACY_MIGRATED)

    def mark_migrated(self) -> None:
        self.store.set_meta(LEGACY_MIGRATED, "1")
