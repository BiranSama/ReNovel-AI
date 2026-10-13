"""向量记忆的存储：SQLite 保存片段原文与向量，检索时用 numpy 计算相似度。

- 每个片段记录生成向量所用的模型；换模型后，旧片段在下次检索该项目时重新生成向量
- 向量生成失败时片段原文照样保存（向量为空），之后检索时补上
- 每个项目的向量矩阵缓存在内存里，写入该项目时失效
"""
import sqlite3
import threading
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS fragments (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    chapter_id TEXT NOT NULL,
    line_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    model TEXT,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_fragments_chapter ON fragments (project_id, chapter_id);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


class VectorStore:
    def __init__(self, db_path: Path):
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._lock = threading.RLock()
        self._cache: dict[tuple[str, str], tuple[list[str], list[str], np.ndarray]] = {}

    # --- 写入 ---
    def replace_chapter(self, project_id: str, chapter_id: str, lines: list[str],
                        model: Optional[str], vectors: Optional[np.ndarray]) -> None:
        """用新的片段替换某一章的全部片段。vectors 为空表示向量稍后再补。"""
        rows = [(project_id, chapter_id, i, line, model if vectors is not None else None,
                 vectors[i].astype(np.float32).tobytes() if vectors is not None else None)
                for i, line in enumerate(lines)]
        with self._lock, self._db:
            self._db.execute("DELETE FROM fragments WHERE project_id = ? AND chapter_id = ?", (project_id, chapter_id))
            self._db.executemany("INSERT INTO fragments (project_id, chapter_id, line_index, text, model, embedding) "
                                 "VALUES (?, ?, ?, ?, ?, ?)", rows)
            self._invalidate(project_id)

    def clone_project(self, old_pid: str, new_pid: str, chapter_map: Optional[dict] = None) -> int:
        """复制项目的全部片段（连同向量）；chapter_map 把原章节 id 换成副本的章节 id。返回复制条数。"""
        with self._lock, self._db:
            rows = self._db.execute("SELECT chapter_id, line_index, text, model, embedding FROM fragments "
                                    "WHERE project_id = ?", (old_pid,)).fetchall()
            mapping = chapter_map or {}
            self._db.executemany("INSERT INTO fragments (project_id, chapter_id, line_index, text, model, embedding) "
                                 "VALUES (?, ?, ?, ?, ?, ?)",
                                 [(new_pid, mapping.get(c, c), i, t, m, e) for c, i, t, m, e in rows])
            self._invalidate(new_pid)
        return len(rows)

    def delete_project(self, project_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM fragments WHERE project_id = ?", (project_id,))
            self._invalidate(project_id)

    def stale(self, project_id: str, model: str, limit: int = 256) -> list[tuple[int, str]]:
        """向量缺失或不是当前模型生成的片段 (id, 原文)。"""
        with self._lock:
            return self._db.execute("SELECT id, text FROM fragments WHERE project_id = ? "
                                    "AND (model IS NULL OR model != ?) LIMIT ?", (project_id, model, limit)).fetchall()

    def set_vectors(self, project_id: str, ids: list[int], model: str, vectors: np.ndarray) -> None:
        with self._lock, self._db:
            self._db.executemany("UPDATE fragments SET model = ?, embedding = ? WHERE id = ?",
                                 [(model, v.astype(np.float32).tobytes(), i) for i, v in zip(ids, vectors)])
            self._invalidate(project_id)

    # --- 读取 ---
    def search(self, project_id: str, model: str, query: np.ndarray, n: int = 5,
               chapter_ids: Optional[Iterable[str]] = None) -> list[str]:
        """与 query 最相似的 n 个片段原文；chapter_ids 不为空时只在这些章节里找。"""
        texts, chapters, matrix = self._matrix(project_id, model)
        if not texts:
            return []
        scores = matrix @ query.astype(np.float32)
        if chapter_ids is not None:
            allowed = set(chapter_ids)
            scores = np.where([c in allowed for c in chapters], scores, -np.inf)
        order = np.argsort(-scores)[:n]
        return [texts[i] for i in order if np.isfinite(scores[i])]

    def chapter_texts(self, project_id: str, chapter_id: str) -> list[str]:
        with self._lock:
            rows = self._db.execute("SELECT text FROM fragments WHERE project_id = ? AND chapter_id = ? "
                                    "ORDER BY line_index", (project_id, chapter_id)).fetchall()
        return [r[0] for r in rows]

    def count(self, project_id: Optional[str] = None) -> int:
        with self._lock:
            if project_id is None:
                return self._db.execute("SELECT COUNT(*) FROM fragments").fetchone()[0]
            return self._db.execute("SELECT COUNT(*) FROM fragments WHERE project_id = ?", (project_id,)).fetchone()[0]

    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _matrix(self, project_id: str, model: str):
        key = (project_id, model)
        with self._lock:
            if key not in self._cache:
                rows = self._db.execute("SELECT text, chapter_id, embedding FROM fragments WHERE project_id = ? "
                                        "AND model = ? ORDER BY id", (project_id, model)).fetchall()
                matrix = np.stack([np.frombuffer(r[2], dtype=np.float32) for r in rows]) if rows else np.zeros((0, 0))
                self._cache[key] = ([r[0] for r in rows], [r[1] for r in rows], matrix)
            return self._cache[key]

    def _invalidate(self, project_id: str) -> None:
        for key in [k for k in self._cache if k[0] == project_id]:
            del self._cache[key]
