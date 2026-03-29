import json
from typing import Optional
from dataclasses import dataclass

from src.domain.entities import PlotEvent, EventType, CharacterState
from src.infrastructure.llm import LLMGateway
from src.shared.types import LLMConfig, LLMRequest, Provider


EXTRACTION_PROMPT = """你是一个小说分析专家。请分析以下文本，提取关键信息。

## 文本内容
{text}

## 已知角色
{characters}

## 请提取以下信息（以 JSON 格式返回）

### 1. 情节事件 (events)
提取文本中的关键事件，每个事件包含：
- event_type: 事件类型 (dialogue/action/revelation/conflict/resolution/turning_point/character_intro/character_exit/relationship_change/location_change/time_skip/flashback/foreshadowing/other)
- title: 事件简短标题
- summary: 事件摘要 (50字以内)
- characters: 涉及的角色名称列表
- location: 发生地点 (如果有)
- importance: 重要程度 1-5
- affects_future: 是否影响后续剧情 (true/false)

### 2. 角色状态变化 (character_changes)
提取每个角色的状态变化，包含：
- character_name: 角色名称
- emotional_state: 情绪状态 (neutral/happy/sad/angry/fearful/surprised/hopeful/despairing/determined/confused/relieved)
- new_knowledge: 新获得的知识/信息
- location: 当前位置
- relationship_changes: 关系变化 (与其他角色的关系)
- secrets: 秘密 (角色知道但未公开的信息)

### 3. 章节摘要 (chapter_summary)
- summary: 本章摘要 (100字以内)
- key_events: 关键事件列表
- key_characters: 主要角色列表

## 返回格式
```json
{{
  "events": [...],
  "character_changes": [...],
  "chapter_summary": {{
    "summary": "...",
    "key_events": [...],
    "key_characters": [...]
  }}
}}
```

只返回 JSON，不要其他内容。"""


@dataclass
class ExtractionResult:
    events: list[PlotEvent]
    character_states: list[CharacterState]
    chapter_summary: dict


class EventExtractor:
    def __init__(self, llm_gateway: LLMGateway, llm_config: LLMConfig):
        self.llm_gateway = llm_gateway
        self.llm_config = llm_config
    
    async def extract(
        self,
        text: str,
        project_id: str,
        chapter_id: str,
        chapter_index: int,
        known_characters: list[dict],
    ) -> ExtractionResult:
        prompt = self._build_prompt(text, known_characters)
        
        request = LLMRequest(
            messages=[{"role": "user", "content": prompt}],
            config=self.llm_config,
            response_format="json",
        )
        
        response = await self.llm_gateway.invoke(request)
        
        return self._parse_result(
            response.content,
            project_id,
            chapter_id,
            chapter_index,
            known_characters,
        )
    
    def _build_prompt(self, text: str, characters: list[dict]) -> str:
        char_info = "\n".join([
            f"- {c.get('name', '未知')}: {c.get('description', '')}"
            for c in characters
        ]) if characters else "暂无已知角色"
        
        return EXTRACTION_PROMPT.format(
            text=text[:6000],
            characters=char_info,
        )
    
    def _parse_result(
        self,
        response_text: str,
        project_id: str,
        chapter_id: str,
        chapter_index: int,
        known_characters: list[dict],
    ) -> ExtractionResult:
        try:
            json_str = self._extract_json(response_text)
            data = json.loads(json_str)
        except json.JSONDecodeError:
            data = {"events": [], "character_changes": [], "chapter_summary": {}}
        
        char_id_map = {c.get("name"): c.get("id") for c in known_characters}
        
        events = []
        for event_data in data.get("events", []):
            try:
                event_type = EventType(event_data.get("event_type", "other"))
            except ValueError:
                event_type = EventType.OTHER
            
            event = PlotEvent.create(
                project_id=project_id,
                chapter_id=chapter_id,
                chapter_index=chapter_index,
                event_type=event_type,
                title=event_data.get("title", "未命名事件"),
                summary=event_data.get("summary", ""),
            )
            event.characters = event_data.get("characters", [])
            event.location = event_data.get("location")
            event.importance = event_data.get("importance", 1)
            event.affects_future = event_data.get("affects_future", False)
            events.append(event)
        
        character_states = []
        for state_data in data.get("character_changes", []):
            char_name = state_data.get("character_name")
            char_id = char_id_map.get(char_name)
            
            if not char_id:
                continue
            
            state = CharacterState.create(
                character_id=char_id,
                project_id=project_id,
                chapter_id=chapter_id,
                chapter_index=chapter_index,
            )
            
            try:
                from src.domain.entities.character_state import EmotionalState
                state.emotional_state = EmotionalState(
                    state_data.get("emotional_state", "neutral")
                )
            except ValueError:
                pass
            
            state.knowledge = state_data.get("new_knowledge", [])
            state.location = state_data.get("location")
            
            for other_name, relation_info in state_data.get("relationship_changes", {}).items():
                other_id = char_id_map.get(other_name)
                if other_id:
                    state.update_relationship(
                        other_id,
                        relation_info.get("relation", "unknown"),
                        relation_info.get("strength", 1.0),
                    )
            
            state.secrets = state_data.get("secrets", [])
            character_states.append(state)
        
        chapter_summary = data.get("chapter_summary", {})
        
        return ExtractionResult(
            events=events,
            character_states=character_states,
            chapter_summary=chapter_summary,
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
