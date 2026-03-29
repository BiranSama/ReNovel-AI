from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import uuid


class EventType(Enum):
    DIALOGUE = "dialogue"
    ACTION = "action"
    REVELATION = "revelation"
    CONFLICT = "conflict"
    RESOLUTION = "resolution"
    TURNING_POINT = "turning_point"
    CHARACTER_INTRO = "character_intro"
    CHARACTER_EXIT = "character_exit"
    RELATIONSHIP_CHANGE = "relationship_change"
    LOCATION_CHANGE = "location_change"
    TIME_SKIP = "time_skip"
    FLASHBACK = "flashback"
    FORESHADOWING = "foreshadowing"
    OTHER = "other"


@dataclass
class PlotEvent:
    id: str
    project_id: str
    chapter_id: str
    chapter_index: int
    event_type: EventType
    title: str
    summary: str
    characters: list[str] = field(default_factory=list)
    location: Optional[str] = None
    story_time: Optional[str] = None
    importance: int = 1
    affects_future: bool = False
    affected_by: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    
    @classmethod
    def create(
        cls,
        project_id: str,
        chapter_id: str,
        chapter_index: int,
        event_type: EventType,
        title: str,
        summary: str,
    ) -> "PlotEvent":
        return cls(
            id=str(uuid.uuid4()),
            project_id=project_id,
            chapter_id=chapter_id,
            chapter_index=chapter_index,
            event_type=event_type,
            title=title,
            summary=summary,
        )
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "chapter_id": self.chapter_id,
            "chapter_index": self.chapter_index,
            "event_type": self.event_type.value,
            "title": self.title,
            "summary": self.summary,
            "characters": self.characters,
            "location": self.location,
            "story_time": self.story_time,
            "importance": self.importance,
            "affects_future": self.affects_future,
            "affected_by": self.affected_by,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PlotEvent":
        return cls(
            id=data["id"],
            project_id=data["project_id"],
            chapter_id=data["chapter_id"],
            chapter_index=data["chapter_index"],
            event_type=EventType(data["event_type"]),
            title=data["title"],
            summary=data["summary"],
            characters=data.get("characters", []),
            location=data.get("location"),
            story_time=data.get("story_time"),
            importance=data.get("importance", 1),
            affects_future=data.get("affects_future", False),
            affected_by=data.get("affected_by", []),
            metadata=data.get("metadata", {}),
        )
