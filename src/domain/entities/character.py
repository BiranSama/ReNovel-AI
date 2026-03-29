from dataclasses import dataclass, field
from typing import Optional
import uuid

from src.shared.types import EntityType


@dataclass
class Character:
    id: str
    project_id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    first_appearance_chapter: Optional[int] = None
    attributes: dict = field(default_factory=dict)
    
    @classmethod
    def create(
        cls,
        project_id: str,
        name: str,
        description: str = ""
    ) -> "Character":
        return cls(
            id=str(uuid.uuid4()),
            project_id=project_id,
            name=name,
            description=description
        )
    
    def add_alias(self, alias: str):
        if alias and alias not in self.aliases and alias != self.name:
            self.aliases.append(alias)
    
    def matches_name(self, query: str) -> bool:
        query = query.strip().lower()
        if query == self.name.lower():
            return True
        return any(query == alias.lower() for alias in self.aliases)
    
    def set_first_appearance(self, chapter_index: int):
        if self.first_appearance_chapter is None or chapter_index < self.first_appearance_chapter:
            self.first_appearance_chapter = chapter_index
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "aliases": self.aliases,
            "description": self.description,
            "first_appearance_chapter": self.first_appearance_chapter,
            "attributes": self.attributes
        }
