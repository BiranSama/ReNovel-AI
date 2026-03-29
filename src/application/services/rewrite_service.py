from dataclasses import dataclass
from typing import Optional, AsyncIterator, Protocol
from enum import Enum
import logging

from src.domain.entities import Character, PlotEvent, CharacterState
from src.infrastructure.llm import LLMGateway
from src.infrastructure.rag import RAGPipeline
from src.infrastructure.memory import (
    EventExtractor,
    ConsistencyChecker,
    RewriteContextBuilder,
    ConsistencyReport,
    ExtractionResult,
)
from src.shared.types import LLMConfig, LLMRequest, Result


logger = logging.getLogger(__name__)


class RewriteMode(Enum):
    POLISH = "polish"
    REWRITE = "rewrite"
    CONTINUE = "continue"
    EXPAND = "expand"
    COMPRESS = "compress"


@dataclass
class RewriteRequest:
    project_id: str
    chapter_id: str
    chapter_index: int
    original_text: str
    instruction: str
    mode: RewriteMode = RewriteMode.POLISH
    enable_consistency_check: bool = True
    enable_memory_extraction: bool = True


@dataclass
class RewriteResult:
    rewritten_text: str
    original_text: str
    instruction: str
    consistency_report: Optional[ConsistencyReport] = None
    extraction_result: Optional[ExtractionResult] = None
    context_used: Optional[str] = None
    tokens_used: int = 0


class MemoryRepositoryProtocol(Protocol):
    async def get_events_before_chapter(self, project_id: str, chapter_index: int) -> list[PlotEvent]: ...
    async def get_events_after_chapter(self, project_id: str, chapter_index: int) -> list[PlotEvent]: ...
    async def get_latest_character_states(self, project_id: str, chapter_index: int) -> list[CharacterState]: ...
    async def save_plot_events(self, events: list[PlotEvent]) -> None: ...
    async def save_character_states(self, states: list[CharacterState]) -> None: ...
    async def save_chapter_summary(self, project_id: str, chapter_id: str, chapter_index: int, summary: str, key_events: list, key_characters: list) -> None: ...


class CharacterRepositoryProtocol(Protocol):
    async def get_characters(self, project_id: str) -> list[dict]: ...


class RewriteService:
    def __init__(
        self,
        llm_gateway: LLMGateway,
        llm_config: LLMConfig,
        rag_pipeline: RAGPipeline,
        event_extractor: EventExtractor,
        consistency_checker: ConsistencyChecker,
        context_builder: RewriteContextBuilder,
        memory_repo: MemoryRepositoryProtocol,
        character_repo: CharacterRepositoryProtocol,
    ):
        self.llm_gateway = llm_gateway
        self.llm_config = llm_config
        self.rag_pipeline = rag_pipeline
        self.event_extractor = event_extractor
        self.consistency_checker = consistency_checker
        self.context_builder = context_builder
        self.memory_repo = memory_repo
        self.character_repo = character_repo
    
    async def rewrite(self, request: RewriteRequest) -> Result[RewriteResult, str]:
        characters = await self._get_characters(request.project_id)
        
        previous_events = await self.memory_repo.get_events_before_chapter(
            request.project_id, request.chapter_index
        )
        future_events = await self.memory_repo.get_events_after_chapter(
            request.project_id, request.chapter_index
        )
        character_states = await self.memory_repo.get_latest_character_states(
            request.project_id, request.chapter_index
        )
        
        context = await self.context_builder.build(
            project_id=request.project_id,
            chapter_id=request.chapter_id,
            chapter_index=request.chapter_index,
            original_text=request.original_text,
            instruction=request.instruction,
            characters=characters,
            previous_events=previous_events,
            future_events=future_events,
            character_states=character_states,
        )
        
        prompt = context.build_prompt()
        
        llm_request = LLMRequest(
            messages=[{"role": "user", "content": prompt}],
            config=self.llm_config,
            stream=False,
        )
        
        try:
            response = await self.llm_gateway.invoke(llm_request)
            rewritten_text = response.content
        except Exception as e:
            logger.error(f"LLM invocation failed: {e}")
            return Result.err(f"LLM 调用失败: {e}")
        
        consistency_report = None
        if request.enable_consistency_check:
            consistency_report = await self.consistency_checker.check(
                rewrite_content=rewritten_text,
                chapter_index=request.chapter_index,
                characters=characters,
                previous_events=previous_events,
                future_events=future_events,
                character_states=character_states,
            )
        
        extraction_result = None
        if request.enable_memory_extraction:
            try:
                extraction_result = await self.event_extractor.extract(
                    text=rewritten_text,
                    project_id=request.project_id,
                    chapter_id=request.chapter_id,
                    chapter_index=request.chapter_index,
                    known_characters=[c.to_dict() for c in characters],
                )
                
                await self.memory_repo.save_plot_events(extraction_result.events)
                await self.memory_repo.save_character_states(extraction_result.character_states)
                
                if extraction_result.chapter_summary:
                    await self.memory_repo.save_chapter_summary(
                        project_id=request.project_id,
                        chapter_id=request.chapter_id,
                        chapter_index=request.chapter_index,
                        summary=extraction_result.chapter_summary.get("summary", ""),
                        key_events=extraction_result.chapter_summary.get("key_events", []),
                        key_characters=extraction_result.chapter_summary.get("key_characters", []),
                    )
            except Exception as e:
                logger.warning(f"Memory extraction failed: {e}")
        
        await self.rag_pipeline.index(
            project_id=request.project_id,
            chapter_id=request.chapter_id,
            text=rewritten_text,
        )
        
        return Result.ok(RewriteResult(
            rewritten_text=rewritten_text,
            original_text=request.original_text,
            instruction=request.instruction,
            consistency_report=consistency_report,
            extraction_result=extraction_result,
            context_used=prompt,
            tokens_used=response.usage.get("total_tokens", 0),
        ))
    
    async def stream_rewrite(self, request: RewriteRequest) -> AsyncIterator[str]:
        characters = await self._get_characters(request.project_id)
        
        previous_events = await self.memory_repo.get_events_before_chapter(
            request.project_id, request.chapter_index
        )
        future_events = await self.memory_repo.get_events_after_chapter(
            request.project_id, request.chapter_index
        )
        character_states = await self.memory_repo.get_latest_character_states(
            request.project_id, request.chapter_index
        )
        
        context = await self.context_builder.build(
            project_id=request.project_id,
            chapter_id=request.chapter_id,
            chapter_index=request.chapter_index,
            original_text=request.original_text,
            instruction=request.instruction,
            characters=characters,
            previous_events=previous_events,
            future_events=future_events,
            character_states=character_states,
        )
        
        prompt = context.build_prompt()
        
        llm_request = LLMRequest(
            messages=[{"role": "user", "content": prompt}],
            config=self.llm_config,
            stream=True,
        )
        
        full_text = ""
        async for chunk in self.llm_gateway.stream(llm_request):
            full_text += chunk
            yield chunk
        
        if request.enable_memory_extraction:
            try:
                extraction_result = await self.event_extractor.extract(
                    text=full_text,
                    project_id=request.project_id,
                    chapter_id=request.chapter_id,
                    chapter_index=request.chapter_index,
                    known_characters=[c.to_dict() for c in characters],
                )
                
                await self.memory_repo.save_plot_events(extraction_result.events)
                await self.memory_repo.save_character_states(extraction_result.character_states)
            except Exception as e:
                logger.warning(f"Memory extraction failed in stream: {e}")
        
        await self.rag_pipeline.index(
            project_id=request.project_id,
            chapter_id=request.chapter_id,
            text=full_text,
        )
    
    async def check_consistency(
        self,
        text: str,
        project_id: str,
        chapter_index: int,
    ) -> Result["ConsistencyReport", str]:
        try:
            characters = await self._get_characters(project_id)
            previous_events = await self.memory_repo.get_events_before_chapter(
                project_id, chapter_index
            )
            future_events = await self.memory_repo.get_events_after_chapter(
                project_id, chapter_index
            )
            character_states = await self.memory_repo.get_latest_character_states(
                project_id, chapter_index
            )
            
            report = await self.consistency_checker.check(
                rewrite_content=text,
                chapter_index=chapter_index,
                characters=characters,
                previous_events=previous_events,
                future_events=future_events,
                character_states=character_states,
            )
            return Result.ok(report)
        except Exception as e:
            logger.error(f"Consistency check failed: {e}")
            return Result.err(f"一致性检查失败: {e}")
    
    async def extract_memory(
        self,
        text: str,
        project_id: str,
        chapter_id: str,
        chapter_index: int,
    ) -> Result[ExtractionResult, str]:
        try:
            characters = await self._get_characters(project_id)
            
            result = await self.event_extractor.extract(
                text=text,
                project_id=project_id,
                chapter_id=chapter_id,
                chapter_index=chapter_index,
                known_characters=[c.to_dict() for c in characters],
            )
            
            await self.memory_repo.save_plot_events(result.events)
            await self.memory_repo.save_character_states(result.character_states)
            
            return Result.ok(result)
        except Exception as e:
            logger.error(f"Memory extraction failed: {e}")
            return Result.err(f"记忆提取失败: {e}")
    
    async def _get_characters(self, project_id: str) -> list[Character]:
        char_data = await self.character_repo.get_characters(project_id)
        return [
            Character(
                id=c["id"],
                project_id=c["project_id"],
                name=c["name"],
                aliases=c.get("aliases", []),
                description=c.get("description", ""),
                first_appearance_chapter=c.get("first_appearance_chapter"),
                attributes=c.get("attributes", {}),
            )
            for c in char_data
        ]
