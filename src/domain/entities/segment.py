from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import uuid


class SegmentStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    REJECTED = "rejected"


@dataclass
class Segment:
    id: str
    chapter_id: str
    original: str
    revised: str = ""
    order_index: int = 0
    status: SegmentStatus = SegmentStatus.PENDING
    instruction: str = ""
    review_score: Optional[float] = None
    review_suggestion: str = ""
    
    @classmethod
    def create(
        cls,
        chapter_id: str,
        original: str,
        order_index: int = 0
    ) -> "Segment":
        return cls(
            id=str(uuid.uuid4()),
            chapter_id=chapter_id,
            original=original,
            order_index=order_index
        )
    
    def set_revised(self, revised: str):
        self.revised = revised
        self.status = SegmentStatus.COMPLETED
    
    def set_processing(self):
        self.status = SegmentStatus.PROCESSING
    
    def set_rejected(self, reason: str = ""):
        self.status = SegmentStatus.REJECTED
        self.review_suggestion = reason
    
    def get_final_text(self) -> str:
        return self.revised if self.revised else self.original
    
    def is_modified(self) -> bool:
        return bool(self.revised) and self.revised != self.original
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "chapter_id": self.chapter_id,
            "original": self.original,
            "revised": self.revised,
            "order_index": self.order_index,
            "status": self.status.value,
            "instruction": self.instruction,
            "review_score": self.review_score,
            "review_suggestion": self.review_suggestion
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Segment":
        return cls(
            id=data["id"],
            chapter_id=data["chapter_id"],
            original=data["original"],
            revised=data.get("revised", ""),
            order_index=data.get("order_index", 0),
            status=SegmentStatus(data.get("status", "pending")),
            instruction=data.get("instruction", ""),
            review_score=data.get("review_score"),
            review_suggestion=data.get("review_suggestion", "")
        )
