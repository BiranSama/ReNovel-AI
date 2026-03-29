from dependency_injector import containers, providers
from typing import Optional

from src.shared.types import LLMConfig, Provider
from src.infrastructure.llm.gateway import LLMGateway
from src.infrastructure.llm.rate_limiter import RateLimiter, RateLimitConfig
from src.infrastructure.llm.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from src.infrastructure.llm.token_counter import TokenCounter
from src.infrastructure.rag.pipeline import RAGPipeline
from src.infrastructure.rag.embedders.local_embedder import LocalEmbedder
from src.infrastructure.rag.chunkers.novel_chunker import NovelChunker
from src.infrastructure.rag.vector_stores.chromadb_store import ChromaDBStore
from src.infrastructure.database.connection import Database
from src.infrastructure.database.repositories.project_repo import SQLiteProjectRepository
from src.infrastructure.database.repositories.chapter_repo import SQLiteChapterRepository
from src.infrastructure.database.repositories.memory_repo import MemoryRepository
from src.infrastructure.memory.event_extractor import EventExtractor
from src.infrastructure.memory.consistency_checker import ConsistencyChecker
from src.infrastructure.memory.rewrite_context_builder import RewriteContextBuilder
from src.application.services.project_service import ProjectService
from src.application.services.chapter_service import ChapterService
from src.application.services.rewrite_service import RewriteService


class Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    
    database = providers.Singleton(
        Database,
        db_path=config.db_path,
    )
    
    rate_limiter = providers.Singleton(
        RateLimiter,
        config=providers.Factory(RateLimitConfig),
    )
    
    circuit_breaker = providers.Singleton(
        CircuitBreaker,
        config=providers.Factory(CircuitBreakerConfig),
    )
    
    token_counter = providers.Singleton(TokenCounter)
    
    llm_gateway = providers.Singleton(
        LLMGateway,
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        token_counter=token_counter,
    )
    
    embedder = providers.Singleton(
        LocalEmbedder,
    )
    
    chunker = providers.Singleton(
        NovelChunker,
        chunk_size=500,
        overlap=50,
    )
    
    vector_store = providers.Singleton(
        ChromaDBStore,
        persist_dir="data/vectordb",
        embedder=embedder,
    )
    
    rag_pipeline = providers.Singleton(
        RAGPipeline,
        embedder=embedder,
        chunker=chunker,
        vector_store=vector_store,
    )
    
    project_repo = providers.Singleton(
        SQLiteProjectRepository,
        db=database,
    )
    
    chapter_repo = providers.Singleton(
        SQLiteChapterRepository,
        db=database,
    )
    
    memory_repo = providers.Singleton(
        MemoryRepository,
        db_connection=database,
    )
    
    event_extractor = providers.Factory(
        EventExtractor,
        llm_gateway=llm_gateway,
        llm_config=config.llm,
    )
    
    consistency_checker = providers.Factory(
        ConsistencyChecker,
        llm_gateway=llm_gateway,
        llm_config=config.llm,
    )
    
    context_builder = providers.Factory(
        RewriteContextBuilder,
        rag_pipeline=rag_pipeline,
        llm_gateway=llm_gateway,
        llm_config=config.llm,
    )
    
    project_service = providers.Singleton(
        ProjectService,
        project_repo=project_repo,
        chapter_repo=chapter_repo,
    )
    
    chapter_service = providers.Singleton(
        ChapterService,
        chapter_repo=chapter_repo,
        rag_pipeline=rag_pipeline,
        memory_repo=memory_repo,
    )
    
    rewrite_service = providers.Factory(
        RewriteService,
        llm_gateway=llm_gateway,
        llm_config=config.llm,
        rag_pipeline=rag_pipeline,
        event_extractor=event_extractor,
        consistency_checker=consistency_checker,
        context_builder=context_builder,
        memory_repo=memory_repo,
        character_repo=project_repo,
    )


container = Container()
container.config.from_dict({
    "db_path": "data/projects.db",
    "llm": {
        "provider": Provider.OPENAI.value,
        "model": "gpt-4",
        "api_key": "",
        "temperature": 0.7,
        "max_tokens": 4096,
    }
})


def configure_container(llm_config: Optional[LLMConfig] = None) -> None:
    if llm_config:
        container.config.from_dict({
            "db_path": "data/projects.db",
            "llm": {
                "provider": llm_config.provider.value,
                "model": llm_config.model,
                "api_key": llm_config.api_key,
                "base_url": llm_config.base_url,
                "temperature": llm_config.temperature,
                "max_tokens": llm_config.max_tokens,
            }
        })


def get_llm_config() -> LLMConfig:
    llm_dict = container.config.llm()
    return LLMConfig(
        provider=Provider(llm_dict.get("provider", "openai")),
        model=llm_dict.get("model", "gpt-4"),
        api_key=llm_dict.get("api_key", ""),
        base_url=llm_dict.get("base_url"),
        temperature=llm_dict.get("temperature", 0.7),
        max_tokens=llm_dict.get("max_tokens", 4096),
    )
