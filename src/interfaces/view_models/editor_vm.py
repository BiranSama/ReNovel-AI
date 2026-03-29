from dataclasses import dataclass, field
from typing import Optional, Any, Callable
from enum import Enum

from src.shared.types import ViewMode


@dataclass
class EditorState:
    segments: list[dict] = field(default_factory=list)
    full_text_draft: str = ""
    view_mode: ViewMode = ViewMode.SEGMENT
    current_chapter_id: Optional[str] = None
    is_dirty: bool = False
    
    def get_merged_text(self) -> str:
        lines = []
        for seg in self.segments:
            content = seg.get("revised") or seg.get("original", "")
            if content.strip():
                lines.append(content)
        return "\n\n".join(lines)
    
    def set_segments(self, segments: list[dict]):
        self.segments = segments
        self.is_dirty = False
    
    def update_segment(self, index: int, field: str, value: str):
        if 0 <= index < len(self.segments):
            self.segments[index][field] = value
            self.is_dirty = True


@dataclass
class ProjectState:
    current_project_id: Optional[str] = None
    current_project_title: str = "未加载小说"
    chapters: list[dict] = field(default_factory=list)
    active_card_name: str = "默认 (无人设)"
    
    def set_project(self, project_id: str, title: str):
        self.current_project_id = project_id
        self.current_project_title = title
    
    def set_chapters(self, chapters: list[dict]):
        self.chapters = chapters


@dataclass
class BatchState:
    is_running: bool = False
    stop_signal: bool = False
    current_task_id: Optional[str] = None
    progress: float = 0.0
    status_message: str = ""


@dataclass
class GraphState:
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    is_building: bool = False


@dataclass
class AppState:
    editor: EditorState = field(default_factory=EditorState)
    project: ProjectState = field(default_factory=ProjectState)
    batch: BatchState = field(default_factory=BatchState)
    graph: GraphState = field(default_factory=GraphState)
    
    ui_refs: dict[str, Any] = field(default_factory=dict)
    
    def reset(self):
        self.editor = EditorState()
        self.project = ProjectState()
        self.batch = BatchState()
        self.graph = GraphState()
        self.ui_refs.clear()


app_state = AppState()
