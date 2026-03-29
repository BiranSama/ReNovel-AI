from dataclasses import dataclass, field
from typing import Optional

from src.domain.entities import PlotEvent, CharacterState, Character
from src.infrastructure.rag import RAGPipeline
from src.infrastructure.llm import LLMGateway
from src.shared.types import LLMConfig, LLMRequest, RetrievalResult


@dataclass
class RewriteContext:
    project_id: str
    chapter_id: str
    chapter_index: int
    original_text: str
    instruction: str
    
    rag_context: str = ""
    previous_summary: str = ""
    next_summary: str = ""
    
    character_info: str = ""
    character_states: str = ""
    
    previous_events: list[PlotEvent] = field(default_factory=list)
    future_events: list[PlotEvent] = field(default_factory=list)
    
    consistency_constraints: str = ""
    
    def build_prompt(self) -> str:
        parts = []
        
        if self.character_info:
            parts.append(f"【角色信息】\n{self.character_info}\n")
        
        if self.character_states:
            parts.append(f"【角色当前状态】\n{self.character_states}\n")
        
        if self.previous_summary:
            parts.append(f"【前文摘要】\n{self.previous_summary}\n")
        
        if self.rag_context:
            parts.append(f"{self.rag_context}\n")
        
        if self.consistency_constraints:
            parts.append(f"【一致性约束】\n{self.consistency_constraints}\n")
        
        if self.next_summary:
            parts.append(f"【后续章节提示】\n{self.next_summary}\n")
        
        context = "\n".join(parts)
        
        return f"""{context}
【改写指令】
{self.instruction}

【原文】
{self.original_text}

请根据以上上下文和指令进行改写，确保：
1. 保持角色性格一致
2. 不与前后情节矛盾
3. 保持文风统一
"""


class RewriteContextBuilder:
    def __init__(
        self,
        rag_pipeline: RAGPipeline,
        llm_gateway: LLMGateway,
        llm_config: LLMConfig,
    ):
        self.rag_pipeline = rag_pipeline
        self.llm_gateway = llm_gateway
        self.llm_config = llm_config
    
    async def build(
        self,
        project_id: str,
        chapter_id: str,
        chapter_index: int,
        original_text: str,
        instruction: str,
        characters: list[Character],
        previous_events: list[PlotEvent] = None,
        future_events: list[PlotEvent] = None,
        character_states: list[CharacterState] = None,
        previous_chapter_summary: str = "",
        next_chapter_summary: str = "",
    ) -> RewriteContext:
        context = RewriteContext(
            project_id=project_id,
            chapter_id=chapter_id,
            chapter_index=chapter_index,
            original_text=original_text,
            instruction=instruction,
        )
        
        rag_result = await self.rag_pipeline.retrieve(
            query=f"{instruction}\n{original_text[:500]}",
            project_id=project_id,
            top_k=5,
        )
        context.rag_context = self.rag_pipeline.format_context(rag_result, max_tokens=1500)
        
        context.character_info = self._format_character_info(characters)
        
        if character_states:
            context.character_states = self._format_character_states(character_states)
        
        context.previous_events = previous_events or []
        context.future_events = future_events or []
        
        context.previous_summary = previous_chapter_summary
        context.next_summary = next_chapter_summary
        
        context.consistency_constraints = self._build_constraints(
            future_events or [],
            character_states or [],
        )
        
        return context
    
    def _format_character_info(self, characters: list[Character]) -> str:
        if not characters:
            return ""
        
        lines = []
        for char in characters:
            aliases = f" (别名: {', '.join(char.aliases)})" if char.aliases else ""
            lines.append(f"- {char.name}{aliases}: {char.description}")
        
        return "\n".join(lines)
    
    def _format_character_states(self, states: list[CharacterState]) -> str:
        if not states:
            return ""
        
        lines = []
        for state in states:
            knowledge = f", 知道: {'; '.join(state.knowledge[:3])}" if state.knowledge else ""
            location = f", 位置: {state.location}" if state.location else ""
            lines.append(
                f"- 情绪: {state.emotional_state.value}{location}{knowledge}"
            )
        
        return "\n".join(lines)
    
    def _build_constraints(
        self,
        future_events: list[PlotEvent],
        character_states: list[CharacterState],
    ) -> str:
        constraints = []
        
        future_chars = set()
        for event in future_events:
            future_chars.update(event.characters)
        
        if future_chars:
            constraints.append(f"以下角色在后续章节仍有出场，请勿写死: {', '.join(future_chars)}")
        
        for state in character_states:
            if state.secrets:
                constraints.append(
                    f"角色 {state.character_id} 知道以下秘密但未公开: {'; '.join(state.secrets[:2])}"
                )
        
        return "\n".join(constraints) if constraints else ""
    
    async def enhance_with_summary(
        self,
        context: RewriteContext,
        previous_content: str = "",
        next_content: str = "",
    ) -> RewriteContext:
        if previous_content and not context.previous_summary:
            context.previous_summary = await self._generate_summary(previous_content, "previous")
        
        if next_content and not context.next_summary:
            context.next_summary = await self._generate_summary(next_content, "next")
        
        return context
    
    async def _generate_summary(self, content: str, position: str) -> str:
        prompt = f"""请用100字以内总结以下章节内容，突出关键情节和角色变化：

{content[:2000]}

只返回摘要，不要其他内容。"""

        request = LLMRequest(
            messages=[{"role": "user", "content": prompt}],
            config=self.llm_config,
        )
        
        try:
            response = await self.llm_gateway.invoke(request)
            return response.content.strip()
        except Exception:
            return ""
