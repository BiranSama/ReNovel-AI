from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from src.domain.entities import PlotEvent, CharacterState, Character
from src.infrastructure.llm import LLMGateway
from src.shared.types import LLMConfig, LLMRequest


class ConsistencyIssueType(Enum):
    CHARACTER_DEATH = "character_death"
    CHARACTER_LOCATION = "character_location"
    KNOWLEDGE_CONFLICT = "knowledge_conflict"
    RELATIONSHIP_CONFLICT = "relationship_conflict"
    TIMELINE_CONFLICT = "timeline_conflict"
    PLOT_HOLE = "plot_hole"
    CHARACTER_PERSONALITY = "character_personality"
    UNRESOLVED_PLOT = "unresolved_plot"


@dataclass
class ConsistencyIssue:
    issue_type: ConsistencyIssueType
    severity: str
    description: str
    chapter_index: int
    details: dict = field(default_factory=dict)
    suggestion: Optional[str] = None


@dataclass
class ConsistencyReport:
    is_consistent: bool
    issues: list[ConsistencyIssue]
    summary: str
    
    def get_critical_issues(self) -> list[ConsistencyIssue]:
        return [i for i in self.issues if i.severity == "critical"]
    
    def get_warnings(self) -> list[ConsistencyIssue]:
        return [i for i in self.issues if i.severity == "warning"]


CONSISTENCY_CHECK_PROMPT = """你是一个小说一致性检查专家。请检查以下改写内容是否与已知信息一致。

## 已知信息

### 角色信息
{character_info}

### 之前章节的关键事件
{previous_events}

### 角色当前状态（改写章节之前）
{character_states}

### 后续章节的关键事件（需要保持一致）
{future_events}

## 待检查的改写内容
章节 {chapter_index}: 
{rewrite_content}

## 请检查以下一致性问题

1. **角色死亡问题**: 角色是否在后续章节出现，但在此章节被写死？
2. **位置冲突**: 角色位置是否与前后章节矛盾？
3. **知识冲突**: 角色是否知道了他们不应该知道的事情？
4. **关系冲突**: 角色关系变化是否与后续章节矛盾？
5. **时间线冲突**: 时间线是否合理？
6. **情节漏洞**: 是否有未解释的跳跃或矛盾？
7. **角色性格**: 角色行为是否符合其性格设定？

## 返回格式 (JSON)
```json
{{
  "is_consistent": true/false,
  "issues": [
    {{
      "issue_type": "character_death/character_location/knowledge_conflict/relationship_conflict/timeline_conflict/plot_hole/character_personality/unresolved_plot",
      "severity": "critical/warning/info",
      "description": "问题描述",
      "details": {{}},
      "suggestion": "修改建议"
    }}
  ],
  "summary": "总体评估"
}}
```

只返回 JSON，不要其他内容。"""


class ConsistencyChecker:
    def __init__(self, llm_gateway: LLMGateway, llm_config: LLMConfig):
        self.llm_gateway = llm_gateway
        self.llm_config = llm_config
    
    async def check(
        self,
        rewrite_content: str,
        chapter_index: int,
        characters: list[Character],
        previous_events: list[PlotEvent],
        future_events: list[PlotEvent],
        character_states: list[CharacterState],
    ) -> ConsistencyReport:
        prompt = self._build_prompt(
            rewrite_content,
            chapter_index,
            characters,
            previous_events,
            future_events,
            character_states,
        )
        
        request = LLMRequest(
            messages=[{"role": "user", "content": prompt}],
            config=self.llm_config,
            response_format="json",
        )
        
        response = await self.llm_gateway.invoke(request)
        
        return self._parse_report(response.content, chapter_index)
    
    def _build_prompt(
        self,
        rewrite_content: str,
        chapter_index: int,
        characters: list[Character],
        previous_events: list[PlotEvent],
        future_events: list[PlotEvent],
        character_states: list[CharacterState],
    ) -> str:
        char_info = "\n".join([
            f"- {c.name}: {c.description}"
            for c in characters
        ]) if characters else "暂无角色信息"
        
        prev_events_info = "\n".join([
            f"- 第{e.chapter_index}章 [{e.event_type.value}]: {e.title} - {e.summary}"
            for e in previous_events[-10:]
        ]) if previous_events else "无之前章节事件"
        
        future_events_info = "\n".join([
            f"- 第{e.chapter_index}章 [{e.event_type.value}]: {e.title} - {e.summary}"
            for e in future_events[:10]
        ]) if future_events else "无后续章节事件"
        
        states_info = "\n".join([
            f"- {state.character_id}: 情绪={state.emotional_state.value}, 位置={state.location}, 知识={state.knowledge[:3]}"
            for state in character_states
        ]) if character_states else "无角色状态信息"
        
        return CONSISTENCY_CHECK_PROMPT.format(
            character_info=char_info,
            previous_events=prev_events_info,
            character_states=states_info,
            future_events=future_events_info,
            chapter_index=chapter_index,
            rewrite_content=rewrite_content[:4000],
        )
    
    def _parse_report(self, response_text: str, chapter_index: int) -> ConsistencyReport:
        import json
        
        try:
            json_str = self._extract_json(response_text)
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return ConsistencyReport(
                is_consistent=True,
                issues=[],
                summary="无法解析检查结果，默认通过",
            )
        
        issues = []
        for issue_data in data.get("issues", []):
            try:
                issue_type = ConsistencyIssueType(
                    issue_data.get("issue_type", "plot_hole")
                )
            except ValueError:
                issue_type = ConsistencyIssueType.PLOT_HOLE
            
            issue = ConsistencyIssue(
                issue_type=issue_type,
                severity=issue_data.get("severity", "warning"),
                description=issue_data.get("description", ""),
                chapter_index=chapter_index,
                details=issue_data.get("details", {}),
                suggestion=issue_data.get("suggestion"),
            )
            issues.append(issue)
        
        return ConsistencyReport(
            is_consistent=data.get("is_consistent", True),
            issues=issues,
            summary=data.get("summary", ""),
        )
    
    def _extract_json(self, text: str) -> str:
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            return text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            return text[start:end].strip()
        else:
            start = text.find("{")
            end = text.rfind("}") + 1
            return text[start:end] if start != -1 else "{}"
    
    def quick_check_character_death(
        self,
        rewrite_content: str,
        future_events: list[PlotEvent],
        characters: list[Character],
    ) -> list[ConsistencyIssue]:
        issues = []
        
        char_names = {c.name.lower() for c in characters}
        char_aliases = {}
        for c in characters:
            for alias in c.aliases:
                char_aliases[alias.lower()] = c.name.lower()
        
        death_indicators = ["死了", "被杀", "身亡", "断气", "咽气", "气绝", "丧命", "遇害", "牺牲"]
        
        future_char_mentions = set()
        for event in future_events:
            for char in event.characters:
                future_char_mentions.add(char.lower())
        
        content_lower = rewrite_content.lower()
        
        for char in characters:
            char_name_lower = char.name.lower()
            
            has_death = any(
                indicator in content_lower and char_name_lower in content_lower
                for indicator in death_indicators
            )
            
            if has_death and char_name_lower in future_char_mentions:
                issues.append(ConsistencyIssue(
                    issue_type=ConsistencyIssueType.CHARACTER_DEATH,
                    severity="critical",
                    description=f"角色 {char.name} 在此章节死亡，但在后续章节中仍有出现",
                    chapter_index=0,
                    details={"character": char.name},
                    suggestion=f"请检查 {char.name} 的死亡设定是否与后续情节冲突",
                ))
        
        return issues
