import pytest
from unittest.mock import MagicMock, AsyncMock

from src.infrastructure.memory.consistency_checker import (
    ConsistencyChecker,
    ConsistencyReport,
    ConsistencyIssue,
    ConsistencyIssueType,
)
from src.domain.entities import Character, PlotEvent, CharacterState
from src.domain.entities.plot_event import EventType
from src.domain.entities.character_state import EmotionalState
from src.shared.types import LLMConfig, LLMResponse, Provider


class TestConsistencyChecker:
    @pytest.fixture
    def consistency_checker(self, mock_llm_gateway, sample_llm_config):
        return ConsistencyChecker(mock_llm_gateway, sample_llm_config)

    @pytest.mark.asyncio
    async def test_check_returns_consistency_report(
        self,
        consistency_checker: ConsistencyChecker,
        sample_characters,
        sample_plot_events,
        sample_character_states,
        mock_llm_gateway,
    ):
        response = LLMResponse(
            content='{"is_consistent": true, "issues": [], "summary": "无一致性问题"}',
            usage={"total_tokens": 100},
            model="gpt-4",
            latency_ms=500,
            finish_reason="stop",
        )
        mock_llm_gateway.invoke = AsyncMock(return_value=response)
        
        report = await consistency_checker.check(
            rewrite_content="张三和李四在咖啡馆聊天。",
            chapter_index=2,
            characters=sample_characters,
            previous_events=sample_plot_events,
            future_events=[],
            character_states=sample_character_states,
        )
        
        assert isinstance(report, ConsistencyReport)
        assert report.is_consistent is True
        assert len(report.issues) == 0

    @pytest.mark.asyncio
    async def test_check_detects_character_death_issue(
        self,
        consistency_checker: ConsistencyChecker,
        sample_characters,
        sample_plot_events,
        sample_character_states,
        mock_llm_gateway,
    ):
        response = LLMResponse(
            content='{"is_consistent": false, "issues": [{"issue_type": "character_death", "severity": "critical", "description": "角色张三在此章节死亡，但在后续章节中仍有出现", "suggestion": "请检查死亡设定"}], "summary": "发现严重一致性问题"}',
            usage={"total_tokens": 100},
            model="gpt-4",
            latency_ms=500,
            finish_reason="stop",
        )
        mock_llm_gateway.invoke = AsyncMock(return_value=response)
        
        report = await consistency_checker.check(
            rewrite_content="张三被车撞死了。",
            chapter_index=2,
            characters=sample_characters,
            previous_events=sample_plot_events,
            future_events=sample_plot_events,
            character_states=sample_character_states,
        )
        
        assert report.is_consistent is False
        assert len(report.issues) == 1
        assert report.issues[0].issue_type == ConsistencyIssueType.CHARACTER_DEATH
        assert report.issues[0].severity == "critical"

    def test_quick_check_character_death_detects_issue(
        self,
        consistency_checker: ConsistencyChecker,
        sample_characters,
        sample_plot_events,
    ):
        future_event = PlotEvent(
            id="event-future",
            project_id="proj-001",
            chapter_id="chap-003",
            chapter_index=3,
            event_type=EventType.DIALOGUE,
            title="后续对话",
            summary="张三和李四继续聊天",
            characters=["张三", "李四"],
            location="街道",
            importance=0.5,
        )
        
        issues = consistency_checker.quick_check_character_death(
            rewrite_content="张三被车撞死了，当场身亡。",
            future_events=[future_event],
            characters=sample_characters,
        )
        
        assert len(issues) == 1
        assert issues[0].issue_type == ConsistencyIssueType.CHARACTER_DEATH

    def test_quick_check_character_death_no_issue_when_no_future(
        self,
        consistency_checker: ConsistencyChecker,
        sample_characters,
    ):
        issues = consistency_checker.quick_check_character_death(
            rewrite_content="张三被车撞死了，当场身亡。",
            future_events=[],
            characters=sample_characters,
        )
        
        assert len(issues) == 0

    def test_extract_json_from_code_block(self, consistency_checker: ConsistencyChecker):
        text = '''```json
{"is_consistent": true, "issues": []}
```'''
        
        result = consistency_checker._extract_json(text)
        
        assert result == '{"is_consistent": true, "issues": []}'

    def test_extract_json_from_plain_text(self, consistency_checker: ConsistencyChecker):
        text = 'Some text before {"is_consistent": true} some text after'
        
        result = consistency_checker._extract_json(text)
        
        assert '{"is_consistent": true}' in result

    def test_parse_report_handles_invalid_json(
        self,
        consistency_checker: ConsistencyChecker,
    ):
        report = consistency_checker._parse_report("invalid json", chapter_index=1)
        
        assert report.is_consistent is True
        assert len(report.issues) == 0


class TestConsistencyReport:
    def test_get_critical_issues(self):
        report = ConsistencyReport(
            is_consistent=False,
            issues=[
                ConsistencyIssue(
                    issue_type=ConsistencyIssueType.CHARACTER_DEATH,
                    severity="critical",
                    description="严重问题",
                    chapter_index=1,
                ),
                ConsistencyIssue(
                    issue_type=ConsistencyIssueType.PLOT_HOLE,
                    severity="warning",
                    description="警告问题",
                    chapter_index=1,
                ),
            ],
            summary="有问题",
        )
        
        critical = report.get_critical_issues()
        warnings = report.get_warnings()
        
        assert len(critical) == 1
        assert len(warnings) == 1
        assert critical[0].severity == "critical"
        assert warnings[0].severity == "warning"

    def test_empty_issues(self):
        report = ConsistencyReport(
            is_consistent=True,
            issues=[],
            summary="无问题",
        )
        
        assert len(report.get_critical_issues()) == 0
        assert len(report.get_warnings()) == 0


class TestConsistencyIssue:
    def test_issue_creation(self):
        issue = ConsistencyIssue(
            issue_type=ConsistencyIssueType.KNOWLEDGE_CONFLICT,
            severity="warning",
            description="角色知道了不该知道的事情",
            chapter_index=5,
            details={"character": "张三", "knowledge": "秘密"},
            suggestion="删除这段描写",
        )
        
        assert issue.issue_type == ConsistencyIssueType.KNOWLEDGE_CONFLICT
        assert issue.severity == "warning"
        assert issue.details["character"] == "张三"
        assert issue.suggestion == "删除这段描写"
