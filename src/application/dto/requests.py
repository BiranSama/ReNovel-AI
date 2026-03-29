from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class CreateProjectRequest:
    title: str
    description: str = ""


@dataclass
class ImportNovelRequest:
    filename: str
    content: str
    build_graph: bool = False


@dataclass
class RewriteSegmentRequest:
    segment_id: str
    instruction: str
    enable_reviewer: bool = False


@dataclass
class RewriteChapterRequest:
    chapter_id: str
    instruction: str
    enable_reviewer: bool = False


@dataclass
class BatchRewriteRequest:
    project_id: str
    chapter_ids: list[str]
    instruction: str
    create_backup: bool = True


@dataclass
class ChatRequest:
    message: str
    mode: str = "chapter"
    project_id: Optional[str] = None
    chapter_id: Optional[str] = None


@dataclass
class BuildGraphRequest:
    project_id: str
    incremental: bool = False


@dataclass
class SaveProgressRequest:
    project_id: str
    chapter_id: str
