"""批量精修：逐章逐段走统一精修流程，按章保存并记录进度，可随时停止、断点续跑。

- 勾选“创建副本”时，在副本上改写，原项目保持原样
- 进度以章为单位：一章全部处理完才保存并记录；中途停止或出错时，
  当前章已改写的部分不保存，下次续跑时从这一章重新开始（避免同一段被精修两次）
"""
from dataclasses import dataclass
from typing import Callable, Optional

from src.llm import LLMError
from src.services.graph import clone_graph
from src.services.refine import RefineRequest

DEFAULT_INSTRUCTION = "精修文本，保持原意，提升文笔。"
BACKUP_SUFFIX = "(批量副本)"


def split_paragraphs(text: str) -> list[str]:
    return [line.strip() for line in text.split("\n") if line.strip()]


def join_paragraphs(paragraphs: list[str]) -> str:
    return "\n\n".join(p for p in paragraphs if p.strip())


@dataclass
class BatchProgress:
    chapter_title: str
    chapters_done: int
    chapters_total: int
    paragraphs_done: int
    paragraphs_total: int

    @property
    def fraction(self) -> float:
        if not self.chapters_total:
            return 1.0
        within = self.paragraphs_done / self.paragraphs_total if self.paragraphs_total else 0
        return (self.chapters_done + within) / self.chapters_total


@dataclass
class BatchOutcome:
    project_id: str
    chapters_done: int
    chapters_total: int
    stopped: bool = False
    error: str = ""
    review_errors: int = 0    # 审校调用失败的段数（不影响改写结果）
    review_rejected: int = 0  # 重试到上限仍未通过审校的段数（保留最后一次改写）


class BatchService:
    def __init__(self, projects, refine, memory=None):
        self.projects = projects  # ProjectManager
        self.refine = refine      # RefinePipeline
        self.memory = memory      # RAGEngine，可选

    async def make_backup(self, project_id: str, suffix: str = BACKUP_SUFFIX) -> tuple[str, dict[str, str]]:
        """复制项目（含向量记忆与知识图谱），返回副本 id 和 原章节 id → 副本章节 id 的映射。"""
        backup_id = await self.projects.duplicate_project(project_id, suffix)
        originals = await self.projects.get_chapters(project_id)
        copies = await self.projects.get_chapters(backup_id)
        mapping = {o["id"]: c["id"] for o, c in zip(originals, copies)}
        if self.memory:
            await self.memory.aclone_project_memory(project_id, backup_id, mapping)
        clone_graph(project_id, backup_id, mapping)
        return backup_id, mapping

    async def remaining_chapters(self, project_id: str) -> list[dict]:
        """还没有被批量精修过的章节（按章累计，单独精修过的某一章不会让前面的章节被跳过）。"""
        chapters = await self.projects.get_chapters(project_id)
        done = set(await self.projects.get_polished_chapter_ids(project_id))
        return [c for c in chapters if c["id"] not in done]

    async def run(
        self,
        project_id: str,
        chapter_ids: list[str],
        instruction: str = DEFAULT_INSTRUCTION,
        on_progress: Optional[Callable[[BatchProgress], None]] = None,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> BatchOutcome:
        chapters = await self.projects.get_chapters(project_id)
        position = {c["id"]: i + 1 for i, c in enumerate(chapters)}
        wanted = set(chapter_ids)
        targets = [c for c in chapters if c["id"] in wanted]
        outcome = BatchOutcome(project_id, 0, len(targets))

        for chapter in targets:
            paragraphs = split_paragraphs(await self.projects.get_chapter_content(chapter["id"]) or "")
            revised = []
            for done, paragraph in enumerate(paragraphs):
                if should_stop():
                    outcome.stopped = True
                    return outcome
                if on_progress:
                    on_progress(BatchProgress(chapter["title"], outcome.chapters_done, len(targets), done, len(paragraphs)))
                request = RefineRequest(text=paragraph, instruction=instruction,
                                        project_id=project_id, chapter_index=position[chapter["id"]])
                try:
                    result = await self.refine.refine(request)
                except LLMError as error:
                    outcome.stopped, outcome.error = True, str(error)
                    return outcome
                if result.review and result.review.error:
                    outcome.review_errors += 1
                elif result.review and not result.review.passed:
                    outcome.review_rejected += 1
                revised.append(result.text.strip() or paragraph)  # 模型返回空时保留原文

            content = join_paragraphs(revised)
            await self.projects.update_chapter_content(chapter["id"], content)
            if self.memory:
                await self.memory.aindex_chapter(project_id, chapter["id"], content)
            await self.projects.save_progress(project_id, chapter["id"])
            outcome.chapters_done += 1

        if on_progress:
            on_progress(BatchProgress("", outcome.chapters_done, len(targets), 0, 0))
        return outcome
