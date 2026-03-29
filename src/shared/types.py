from dataclasses import dataclass, field
from typing import (
    TypeVar, Generic, Optional, Callable, Any,
    AsyncIterator, Awaitable, Union, Literal
)
from abc import ABC, abstractmethod
from enum import Enum
from datetime import datetime
import uuid

T = TypeVar('T')
E = TypeVar('E')

class Provider(Enum):
    OPENAI = "openai"
    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    LOCAL = "local"

class ProjectStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"

class ViewMode(Enum):
    SEGMENT = "segment"
    FULL = "full"

class BatchStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"

class EntityType(Enum):
    CHARACTER = "character"
    LOCATION = "location"
    ITEM = "item"
    ORGANIZATION = "organization"
    EVENT = "event"
    CONCEPT = "concept"

class RelationType(Enum):
    FAMILY = "family"
    FRIEND = "friend"
    ENEMY = "enemy"
    LOVER = "lover"
    ALLY = "ally"
    OWNS = "owns"
    LOCATED = "located"
    PARTICIPATES = "participates"
    CAUSES = "causes"
    MENTIONS = "mentions"

@dataclass
class Result(Generic[T, E]):
    success: bool
    value: Optional[T] = None
    error: Optional[E] = None
    
    @classmethod
    def ok(cls, value: T) -> "Result[T, E]":
        return cls(success=True, value=value)
    
    @classmethod
    def err(cls, error: E) -> "Result[T, E]":
        return cls(success=False, error=error)
    
    def is_ok(self) -> bool:
        return self.success
    
    def is_err(self) -> bool:
        return not self.success
    
    def unwrap(self) -> T:
        if not self.success:
            raise ValueError(f"Called unwrap on error: {self.error}")
        return self.value
    
    def unwrap_or(self, default: T) -> T:
        return self.value if self.success else default

@dataclass
class LLMConfig:
    provider: Provider
    model: str
    api_key: str
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: float = 60.0
    max_retries: int = 3
    proxy: Optional[str] = None

@dataclass
class LLMRequest:
    messages: list[dict]
    config: LLMConfig
    response_format: Optional[Literal["json", "text"]] = None
    stream: bool = False

@dataclass
class LLMResponse:
    content: str
    usage: dict
    model: str
    latency_ms: float
    finish_reason: str

@dataclass
class Chunk:
    id: str
    content: str
    metadata: dict
    embedding: Optional[list[float]] = None
    parent_id: Optional[str] = None
    child_ids: list[str] = field(default_factory=list)

@dataclass
class RetrievalResult:
    chunks: list[Chunk]
    scores: list[float]
    query: str
    total_tokens: int

@dataclass
class PromptBlock:
    persona: str = ""
    objective: str = ""
    style: str = ""
    constraints: str = ""
    examples: list[str] = field(default_factory=list)

@dataclass
class RewriteContext:
    original_text: str
    instruction: str
    chapter_index: int
    project_id: str = ""
    rag_context: str = ""
    graph_context: str = ""
    character_info: str = ""
    enable_reviewer: bool = False

@dataclass
class RewriteResult:
    rewritten_text: str
    review_score: Optional[float] = None
    review_suggestion: Optional[str] = None
    tokens_used: int = 0

@dataclass
class BatchTask:
    id: str
    project_id: str
    chapter_ids: list[str]
    instruction: str
    status: BatchStatus = BatchStatus.PENDING
    progress: float = 0.0
    current_chapter: Optional[str] = None
    error: Optional[str] = None
    
    @classmethod
    def create(cls, project_id: str, chapter_ids: list[str], instruction: str) -> "BatchTask":
        return cls(
            id=str(uuid.uuid4()),
            project_id=project_id,
            chapter_ids=chapter_ids,
            instruction=instruction
        )

@dataclass
class ChatMessage:
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class GraphNode:
    id: str
    name: str
    type: EntityType
    description: str = ""
    first_appearance: int = 1
    mention_count: int = 1
    attributes: dict = field(default_factory=dict)

@dataclass
class GraphEdge:
    id: str
    source_id: str
    target_id: str
    relation: RelationType
    description: str = ""
    start_chapter: int = 1
    reveal_chapter: Optional[int] = None
    is_secret: bool = False
    confidence: float = 1.0

@dataclass
class GraphData:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
