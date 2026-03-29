from dataclasses import dataclass, field
from typing import Optional
import os
import json


@dataclass
class Settings:
    db_path: str = "data/projects/novelforge.db"
    vectordb_path: str = "data/vectordb"
    config_path: str = "data/config"
    presets_path: str = "data/presets"
    
    default_provider: str = "openai"
    default_model: str = "gpt-4o"
    default_temperature: float = 0.7
    default_max_tokens: int = 4096
    
    rate_limit_rpm: int = 60
    rate_limit_tpm: int = 90000
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 30.0
    
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    rag_top_k: int = 5
    
    server_host: str = "0.0.0.0"
    server_port: int = 8080
    debug: bool = False
    
    log_level: str = "INFO"
    log_format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    log_date_format: str = "%H:%M:%S"
    
    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=os.getenv("NOVELFORGE_DB_PATH", "data/projects/novelforge.db"),
            vectordb_path=os.getenv("NOVELFORGE_VECTORDB_PATH", "data/vectordb"),
            default_provider=os.getenv("NOVELFORGE_PROVIDER", "openai"),
            default_model=os.getenv("NOVELFORGE_MODEL", "gpt-4o"),
            server_port=int(os.getenv("NOVELFORGE_PORT", "8080")),
            debug=os.getenv("NOVELFORGE_DEBUG", "false").lower() == "true",
            log_level=os.getenv("NOVELFORGE_LOG_LEVEL", "INFO"),
            log_format=os.getenv("NOVELFORGE_LOG_FORMAT", "%(asctime)s [%(levelname)s] %(name)s: %(message)s"),
            log_date_format=os.getenv("NOVELFORGE_LOG_DATE_FORMAT", "%H:%M:%S"),
        )
    
    @classmethod
    def from_file(cls, path: str) -> "Settings":
        if not os.path.exists(path):
            return cls()
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})
    
    def to_file(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=2)


settings = Settings.from_env()
