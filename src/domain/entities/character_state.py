from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import uuid


class EmotionalState(Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    SURPRISED = "surprised"
    DISGUSTED = "disgusted"
    HOPEFUL = "hopeful"
    DESPAIRING = "despairing"
    DETERMINED = "determined"
    CONFUSED = "confused"
    RELIEVED = "relieved"


@dataclass
class CharacterState:
    id: str
    character_id: str
    project_id: str
    chapter_id: str
    chapter_index: int
    emotional_state: EmotionalState = EmotionalState.NEUTRAL
    knowledge: list[str] = field(default_factory=list)
    beliefs: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    location: Optional[str] = None
    relationships: dict = field(default_factory=dict)
    physical_state: str = "healthy"
    inventory: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)
    notes: str = ""
    
    @classmethod
    def create(
        cls,
        character_id: str,
        project_id: str,
        chapter_id: str,
        chapter_index: int,
    ) -> "CharacterState":
        return cls(
            id=str(uuid.uuid4()),
            character_id=character_id,
            project_id=project_id,
            chapter_id=chapter_id,
            chapter_index=chapter_index,
        )
    
    def update_relationship(self, other_character_id: str, relation: str, strength: float = 1.0):
        self.relationships[other_character_id] = {
            "relation": relation,
            "strength": strength,
        }
    
    def add_knowledge(self, info: str):
        if info and info not in self.knowledge:
            self.knowledge.append(info)
    
    def add_secret(self, secret: str):
        if secret and secret not in self.secrets:
            self.secrets.append(secret)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "character_id": self.character_id,
            "project_id": self.project_id,
            "chapter_id": self.chapter_id,
            "chapter_index": self.chapter_index,
            "emotional_state": self.emotional_state.value,
            "knowledge": self.knowledge,
            "beliefs": self.beliefs,
            "goals": self.goals,
            "location": self.location,
            "relationships": self.relationships,
            "physical_state": self.physical_state,
            "inventory": self.inventory,
            "secrets": self.secrets,
            "notes": self.notes,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "CharacterState":
        return cls(
            id=data["id"],
            character_id=data["character_id"],
            project_id=data["project_id"],
            chapter_id=data["chapter_id"],
            chapter_index=data["chapter_index"],
            emotional_state=EmotionalState(data.get("emotional_state", "neutral")),
            knowledge=data.get("knowledge", []),
            beliefs=data.get("beliefs", []),
            goals=data.get("goals", []),
            location=data.get("location"),
            relationships=data.get("relationships", {}),
            physical_state=data.get("physical_state", "healthy"),
            inventory=data.get("inventory", []),
            secrets=data.get("secrets", []),
            notes=data.get("notes", ""),
        )
