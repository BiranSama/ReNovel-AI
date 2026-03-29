from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid

from src.shared.types import ProjectStatus


@dataclass
class Project:
    id: str
    title: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    settings: dict = field(default_factory=dict)
    
    @classmethod
    def create(cls, title: str, description: str = "") -> "Project":
        return cls(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            status=ProjectStatus.ACTIVE
        )
    
    def update_title(self, new_title: str):
        self.title = new_title
        self.updated_at = datetime.now()
    
    def update_settings(self, settings: dict):
        self.settings = {**self.settings, **settings}
        self.updated_at = datetime.now()
    
    def archive(self):
        self.status = ProjectStatus.ARCHIVED
        self.updated_at = datetime.now()
    
    def is_archived(self) -> bool:
        return self.status == ProjectStatus.ARCHIVED
