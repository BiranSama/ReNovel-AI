import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Generator

from src.shared.types import (
    LLMConfig, LLMRequest, LLMResponse, Provider, Result
)
from src.domain.entities import Character, PlotEvent, CharacterState
from src.domain.entities.plot_event import EventType
from src.domain.entities.character_state import EmotionalState


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_llm_config() -> LLMConfig:
    return LLMConfig(
        provider=Provider.OPENAI,
        model="gpt-4",
        api_key="test-api-key-12345",
        temperature=0.7,
        max_tokens=4096,
    )


@pytest.fixture
def sample_llm_response() -> LLMResponse:
    return LLMResponse(
        content='{"is_consistent": true, "issues": [], "summary": "无一致性问题"}',
        usage={"total_tokens": 100, "prompt_tokens": 50, "completion_tokens": 50},
        model="gpt-4",
        latency_ms=500.0,
        finish_reason="stop",
    )


@pytest.fixture
def mock_llm_gateway(sample_llm_response: LLMResponse):
    gateway = MagicMock()
    gateway.invoke = AsyncMock(return_value=sample_llm_response)
    gateway.stream = AsyncMock(return_value=iter(["chunk1", "chunk2"]))
    return gateway


@pytest.fixture
def mock_rag_pipeline():
    pipeline = MagicMock()
    pipeline.index = AsyncMock(return_value=5)
    pipeline.retrieve = AsyncMock(return_value=MagicMock(
        chunks=[],
        scores=[],
        query="test",
        total_tokens=0,
    ))
    return pipeline


@pytest.fixture
def sample_character() -> Character:
    return Character(
        id="char-001",
        project_id="proj-001",
        name="张三",
        aliases=["小张", "老张"],
        description="主角，性格开朗",
        first_appearance_chapter=1,
        attributes={"age": 25, "gender": "male"},
    )


@pytest.fixture
def sample_characters(sample_character: Character) -> list[Character]:
    char2 = Character(
        id="char-002",
        project_id="proj-001",
        name="李四",
        aliases=["小李"],
        description="配角，张三的朋友",
        first_appearance_chapter=1,
        attributes={"age": 28, "gender": "male"},
    )
    return [sample_character, char2]


@pytest.fixture
def sample_plot_event() -> PlotEvent:
    return PlotEvent(
        id="event-001",
        project_id="proj-001",
        chapter_id="chap-001",
        chapter_index=1,
        event_type=EventType.DIALOGUE,
        title="初次相遇",
        summary="张三和李四在咖啡馆相遇",
        characters=["张三", "李四"],
        location="咖啡馆",
        importance=0.8,
    )


@pytest.fixture
def sample_plot_events(sample_plot_event: PlotEvent) -> list[PlotEvent]:
    event2 = PlotEvent(
        id="event-002",
        project_id="proj-001",
        chapter_id="chap-002",
        chapter_index=2,
        event_type=EventType.CONFLICT,
        title="争吵",
        summary="张三和李四发生争执",
        characters=["张三", "李四"],
        location="街道",
        importance=0.7,
    )
    return [sample_plot_event, event2]


@pytest.fixture
def sample_character_state() -> CharacterState:
    return CharacterState(
        id="state-001",
        character_id="char-001",
        project_id="proj-001",
        chapter_id="chap-001",
        chapter_index=1,
        emotional_state=EmotionalState.HAPPY,
        location="咖啡馆",
        knowledge=["知道李四的名字"],
        relationships={"李四": {"relation": "friend", "strength": 1.0}},
    )


@pytest.fixture
def sample_character_states(sample_character_state: CharacterState) -> list[CharacterState]:
    state2 = CharacterState(
        id="state-002",
        character_id="char-002",
        project_id="proj-001",
        chapter_id="chap-001",
        chapter_index=1,
        emotional_state=EmotionalState.NEUTRAL,
        location="咖啡馆",
        knowledge=["知道张三的名字"],
        relationships={"张三": {"relation": "friend", "strength": 1.0}},
    )
    return [sample_character_state, state2]


@pytest.fixture
def sample_novel_text() -> str:
    return """
第一章 初遇

阳光透过咖啡馆的玻璃窗洒落，张三推门而入。

"欢迎光临！"店员热情地招呼。

张三环顾四周，发现角落里坐着一个熟悉的身影——李四，他的大学同学。

"李四？好久不见！"张三走过去打招呼。

李四抬起头，露出惊喜的表情："张三！真的是你，快坐快坐。"

两人相谈甚欢，回忆起大学时光的点点滴滴。

"对了，你现在在哪里工作？"张三问道。

"我在一家科技公司做产品经理，"李四回答，"你呢？"

"我是一名自由撰稿人，"张三笑了笑，"终于实现了自己的梦想。"

时间飞逝，不知不觉已是傍晚。

"下次再聚！"两人挥手告别，各自踏上归途。
""".strip()


@pytest.fixture
def sample_rewrite_request():
    from src.application.services.rewrite_service import RewriteRequest, RewriteMode
    return RewriteRequest(
        project_id="proj-001",
        chapter_id="chap-001",
        chapter_index=1,
        original_text="张三走进咖啡馆，看到了李四。",
        instruction="润色这段文字，使其更加生动",
        mode=RewriteMode.POLISH,
        enable_consistency_check=True,
        enable_memory_extraction=True,
    )


@pytest.fixture
def mock_memory_repo():
    with patch("src.infrastructure.database.repositories.memory_repo.memory_repo") as mock:
        mock.get_events_before_chapter = AsyncMock(return_value=[])
        mock.get_events_after_chapter = AsyncMock(return_value=[])
        mock.get_latest_character_states = AsyncMock(return_value=[])
        mock.save_plot_events = AsyncMock()
        mock.save_character_states = AsyncMock()
        mock.save_chapter_summary = AsyncMock()
        yield mock


@pytest.fixture
def mock_project_repo():
    with patch("src.infrastructure.database.repositories.project_repo.project_repo") as mock:
        mock.get_characters = AsyncMock(return_value=[])
        yield mock
