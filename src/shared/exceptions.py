from typing import Optional, Any

class NovelForgeError(Exception):
    """Base error for all application errors"""
    
    def __init__(self, message: str, code: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.code = code or "UNKNOWN_ERROR"
        self.details = details or {}

class ValidationError(NovelForgeError):
    pass

class NotFoundError(NovelForgeError):
    pass

class AuthenticationError(NovelForgeError):
    pass

class RateLimitError(NovelForgeError):
    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[float] = None):
        super().__init__(message, code="RATE_LIMIT")
        self.retry_after = retry_after

class LLMError(NovelForgeError):
    pass

class LLMConnectionError(LLMError):
    pass

class LLMResponseError(LLMError):
    pass

class LLMTimeoutError(LLMError):
    pass

class RAGError(NovelForgeError):
    pass

class RAGIndexingError(RAGError):
    pass

class RAGRetrievalError(RAGError):
    pass

class GraphError(NovelForgeError):
    pass

class GraphExtractionError(GraphError):
    pass

class DatabaseError(NovelForgeError):
    pass

class DatabaseConnectionError(DatabaseError):
    pass

class DatabaseQueryError(DatabaseError):
    pass

class ConfigurationError(NovelForgeError):
    pass

class ImportExportError(NovelForgeError):
    pass

class BatchError(NovelForgeError):
    pass

class BatchCancelledError(BatchError):
    pass
