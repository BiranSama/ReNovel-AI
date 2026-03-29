import pytest
from unittest.mock import AsyncMock, MagicMock
import json

from src.infrastructure.memory.event_extractor import EventExtractor, ExtractionResult
from src.domain.entities import PlotEvent, CharacterState
from src.domain.entities.plot_event import EventType
from src.shared.types import LLMConfig, LLMResponse, Provider


@pytest.fixture
def sample_llm_config():
    return LLMConfig(
        provider=Provider.OPENAI,
        model="gpt-4",
        api_key="test-key",
        temperature=0.7,
        max_tokens=4096,
    )


@pytest.fixture
def mock_llm_gateway():
    gateway = MagicMock()
    gateway.invoke = AsyncMock()
    return gateway


@pytest.fixture
def event_extractor(mock_llm_gateway, sample_llm_config):
    return EventExtractor(
        llm_gateway=mock_llm_gateway,
        llm_config=sample_llm_config,
    )


@pytest.fixture
def sample_extraction_response():
    return json.dumps({
        "events": [
            {
                "event_type": "dialogue",
                "title": "初次对话",
                "summary": "张三和李四交谈",
                "characters": ["张三", "李四"],
                "location": "咖啡馆",
                "importance": 3,
                "affects_future": True,
            },
            {
                "event_type": "action",
                "title": "离开",
                "summary": "张三离开咖啡馆",
                "characters": ["张三"],
                "location": "咖啡馆",
                "importance": 2,
                "affects_future": False,
            },
        ],
        "character_changes": [
            {
                "character_name": "张三",
                "emotional_state": "happy",
                "new_knowledge": ["知道李四的工作"],
                "location": "咖啡馆",
                "relationship_changes": {},
                "secrets": [],
            },
        ],
        "chapter_summary": {
            "summary": "张三和李四在咖啡馆相遇并交谈",
            "key_events": ["初次对话", "离开"],
            "key_characters": ["张三", "李四"],
        },
    })


@pytest.fixture
def known_characters():
    return [
        {"id": "char-001", "name": "张三", "description": "主角"},
        {"id": "char-002", "name": "李四", "description": "配角"},
    ]


class TestEventExtractor:
    @pytest.mark.asyncio
    async def test_extract_success(
        self,
        event_extractor,
        mock_llm_gateway,
        sample_extraction_response,
        known_characters,
    ):
        mock_llm_gateway.invoke.return_value = LLMResponse(
            content=sample_extraction_response,
            usage={"total_tokens": 100},
            model="gpt-4",
            latency_ms=100.0,
            finish_reason="stop",
        )
        
        result = await event_extractor.extract(
            text="张三走进咖啡馆，看到了李四。",
            project_id="proj-001",
            chapter_id="chap-001",
            chapter_index=1,
            known_characters=known_characters,
        )
        
        assert isinstance(result, ExtractionResult)
        assert len(result.events) == 2
        assert len(result.character_states) == 1
        assert result.chapter_summary["summary"] == "张三和李四在咖啡馆相遇并交谈"
    
    @pytest.mark.asyncio
    async def test_extract_events_parsed_correctly(
        self,
        event_extractor,
        mock_llm_gateway,
        sample_extraction_response,
        known_characters,
    ):
        mock_llm_gateway.invoke.return_value = LLMResponse(
            content=sample_extraction_response,
            usage={"total_tokens": 100},
            model="gpt-4",
            latency_ms=100.0,
            finish_reason="stop",
        )
        
        result = await event_extractor.extract(
            text="测试文本",
            project_id="proj-001",
            chapter_id="chap-001",
            chapter_index=1,
            known_characters=known_characters,
        )
        
        event = result.events[0]
        assert isinstance(event, PlotEvent)
        assert event.event_type == EventType.DIALOGUE
        assert event.title == "初次对话"
        assert "张三" in event.characters
    
    @pytest.mark.asyncio
    async def test_extract_invalid_event_type(
        self,
        event_extractor,
        mock_llm_gateway,
        known_characters,
    ):
        response = json.dumps({
            "events": [
                {
                    "event_type": "invalid_type",
                    "title": "测试",
                    "summary": "摘要",
                    "characters": [],
                    "importance": 1,
                },
            ],
            "character_changes": [],
            "chapter_summary": {},
        })
        mock_llm_gateway.invoke.return_value = LLMResponse(
            content=response,
            usage={"total_tokens": 100},
            model="gpt-4",
            latency_ms=100.0,
            finish_reason="stop",
        )
        
        result = await event_extractor.extract(
            text="测试",
            project_id="proj-001",
            chapter_id="chap-001",
            chapter_index=1,
            known_characters=known_characters,
        )
        
        assert len(result.events) == 1
        assert result.events[0].event_type == EventType.OTHER
    
    @pytest.mark.asyncio
    async def test_extract_json_in_code_block(
        self,
        event_extractor,
        mock_llm_gateway,
        sample_extraction_response,
        known_characters,
    ):
        response = f"```json\n{sample_extraction_response}\n```"
        mock_llm_gateway.invoke.return_value = LLMResponse(
            content=response,
            usage={"total_tokens": 100},
            model="gpt-4",
            latency_ms=100.0,
            finish_reason="stop",
        )
        
        result = await event_extractor.extract(
            text="测试",
            project_id="proj-001",
            chapter_id="chap-001",
            chapter_index=1,
            known_characters=known_characters,
        )
        
        assert len(result.events) == 2
    
    @pytest.mark.asyncio
    async def test_extract_invalid_json(
        self,
        event_extractor,
        mock_llm_gateway,
        known_characters,
    ):
        mock_llm_gateway.invoke.return_value = LLMResponse(
            content="这不是有效的JSON",
            usage={"total_tokens": 100},
            model="gpt-4",
            latency_ms=100.0,
            finish_reason="stop",
        )
        
        result = await event_extractor.extract(
            text="测试",
            project_id="proj-001",
            chapter_id="chap-001",
            chapter_index=1,
            known_characters=known_characters,
        )
        
        assert isinstance(result, ExtractionResult)
        assert len(result.events) == 0
        assert len(result.character_states) == 0
    
    @pytest.mark.asyncio
    async def test_extract_character_state(
        self,
        event_extractor,
        mock_llm_gateway,
        sample_extraction_response,
        known_characters,
    ):
        mock_llm_gateway.invoke.return_value = LLMResponse(
            content=sample_extraction_response,
            usage={"total_tokens": 100},
            model="gpt-4",
            latency_ms=100.0,
            finish_reason="stop",
        )
        
        result = await event_extractor.extract(
            text="测试",
            project_id="proj-001",
            chapter_id="chap-001",
            chapter_index=1,
            known_characters=known_characters,
        )
        
        assert len(result.character_states) == 1
        state = result.character_states[0]
        assert isinstance(state, CharacterState)
        assert state.character_id == "char-001"
    
    @pytest.mark.asyncio
    async def test_extract_unknown_character_skipped(
        self,
        event_extractor,
        mock_llm_gateway,
        known_characters,
    ):
        response = json.dumps({
            "events": [],
            "character_changes": [
                {
                    "character_name": "未知角色",
                    "emotional_state": "happy",
                },
            ],
            "chapter_summary": {},
        })
        mock_llm_gateway.invoke.return_value = LLMResponse(
            content=response,
            usage={"total_tokens": 100},
            model="gpt-4",
            latency_ms=100.0,
            finish_reason="stop",
        )
        
        result = await event_extractor.extract(
            text="测试",
            project_id="proj-001",
            chapter_id="chap-001",
            chapter_index=1,
            known_characters=known_characters,
        )
        
        assert len(result.character_states) == 0
    
    @pytest.mark.asyncio
    async def test_extract_empty_characters(
        self,
        event_extractor,
        mock_llm_gateway,
    ):
        mock_llm_gateway.invoke.return_value = LLMResponse(
            content=json.dumps({"events": [], "character_changes": [], "chapter_summary": {}}),
            usage={"total_tokens": 100},
            model="gpt-4",
            latency_ms=100.0,
            finish_reason="stop",
        )
        
        result = await event_extractor.extract(
            text="测试",
            project_id="proj-001",
            chapter_id="chap-001",
            chapter_index=1,
            known_characters=[],
        )
        
        assert isinstance(result, ExtractionResult)
    
    def test_build_prompt(self, event_extractor):
        prompt = event_extractor._build_prompt(
            text="测试文本",
            characters=[{"name": "张三", "description": "主角"}],
        )
        
        assert "测试文本" in prompt
        assert "张三" in prompt
        assert "JSON" in prompt
    
    def test_build_prompt_empty_characters(self, event_extractor):
        prompt = event_extractor._build_prompt(
            text="测试文本",
            characters=[],
        )
        
        assert "暂无已知角色" in prompt
    
    def test_extract_json_from_code_block(self, event_extractor):
        text = "```json\n{\"key\": \"value\"}\n```"
        result = event_extractor._extract_json(text)
        
        assert result == '{"key": "value"}'
    
    def test_extract_json_from_plain_block(self, event_extractor):
        text = "```\n{\"key\": \"value\"}\n```"
        result = event_extractor._extract_json(text)
        
        assert result == '{"key": "value"}'
    
    def test_extract_json_from_raw_text(self, event_extractor):
        text = '前面内容 {"key": "value"} 后面内容'
        result = event_extractor._extract_json(text)
        
        assert result == '{"key": "value"}'
    
    def test_extract_json_no_json(self, event_extractor):
        text = "没有JSON的文本"
        result = event_extractor._extract_json(text)
        
        assert result == "{}"
