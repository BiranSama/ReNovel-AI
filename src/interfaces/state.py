from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from enum import Enum


class ViewMode(Enum):
    SEGMENT = "segment"
    FULL = "full"


@dataclass
class AppState:
    current_project_id: Optional[str] = None
    current_project_title: str = ""
    current_chapter_id: Optional[str] = None
    current_chapter_index: int = 0
    segments: list[dict] = field(default_factory=list)
    full_text_draft: str = ""
    view_mode: ViewMode = ViewMode.SEGMENT
    ui: dict = field(default_factory=dict)
    settings: Any = None
    
    def reset(self) -> None:
        self.current_project_id = None
        self.current_project_title = ""
        self.current_chapter_id = None
        self.current_chapter_index = 0
        self.segments = []
        self.full_text_draft = ""
        self.view_mode = ViewMode.SEGMENT
        self.ui = {}


app_state = AppState()
