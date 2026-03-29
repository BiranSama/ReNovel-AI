from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class Chapter:
    id: str
    project_id: str
    title: str
    order_index: int
    content: str = ""
    word_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)
    
    @classmethod
    def create(
        cls,
        project_id: str,
        title: str,
        order_index: int,
        content: str = ""
    ) -> "Chapter":
        return cls(
            id=str(uuid.uuid4()),
            project_id=project_id,
            title=title,
            order_index=order_index,
            content=content,
            word_count=len(content)
        )
    
    def update_content(self, content: str):
        self.content = content
        self.word_count = len(content)
        self.updated_at = datetime.now()
    
    def append_content(self, text: str):
        self.content += text
        self.word_count = len(self.content)
        self.updated_at = datetime.now()
    
    def is_empty(self) -> bool:
        return len(self.content.strip()) == 0
    
    def get_excerpt(self, max_length: int = 200) -> str:
        if len(self.content) <= max_length:
            return self.content
        return self.content[:max_length] + "..."
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "order_index": self.order_index,
            "content": self.content,
            "word_count": self.word_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }
