# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-03-30

### 🎉 Major Release - Complete Architecture Refactoring

This is a **complete rewrite** of the project architecture, moving from a monolithic structure to a clean Domain-Driven Design (DDD) architecture.

### Added

#### Architecture
- **DDD Four-Layer Architecture**: Domain, Application, Infrastructure, Interfaces
- **Dependency Injection**: Using `dependency_injector` framework for proper IoC container
- **Protocol Interfaces**: Type-safe interfaces using Python's `@runtime_checkable` Protocol
- **Repository Pattern**: Clean separation between domain and data access

#### Infrastructure
- **LLM Gateway**: Unified interface for OpenAI and Google Gemini
- **Circuit Breaker**: Fault tolerance with configurable failure threshold
- **Rate Limiter**: Sliding window algorithm for API rate limiting
- **Retry Mechanism**: Automatic retry with exponential backoff using `tenacity`
- **RAG Pipeline**: Retrieval-Augmented Generation with ChromaDB vector store

#### Memory System
- **Event Extractor**: Automatic extraction of plot events and character states
- **Consistency Checker**: Detects OOC (Out of Character) and plot inconsistencies
- **Context Builder**: Builds rich context for rewriting with memory retrieval

#### Testing
- **97 Unit Tests**: Comprehensive test coverage for core modules
- **Test Fixtures**: Reusable mock objects and sample data
- **Async Test Support**: Full async/await testing with pytest-asyncio

#### Security
- **Input Validation**: UUID validation, path traversal protection
- **API Key Masking**: Secure display of sensitive credentials
- **HTML Sanitization**: Protection against XSS in user inputs

#### Developer Experience
- **Prompt Templates**: YAML-based prompt management with `PromptManager`
- **Structured Logging**: Unified logging with `ConsoleLogger`
- **Type Annotations**: Full type hints across the codebase
- **Result Pattern**: Functional error handling with `Result[T, E]`

### Changed

#### Breaking Changes
- **Removed Old Code**: Deleted `src/core/`, `src/logic/`, `src/ui/` legacy modules
- **New DI Container**: All services now managed through `src/di/container.py`
- **Service Signatures**: All service methods now return `Result` type

#### Improvements
- **Batch Insert**: Fixed N+1 queries with `executemany` for bulk operations
- **Error Handling**: Consistent error handling with `Result` pattern
- **Code Organization**: Clear module boundaries following DDD principles

### Migration Guide

If you're upgrading from v0.2.0:

1. **Database**: Existing SQLite databases are compatible
2. **Configuration**: Update to use the new DI container initialization
3. **API Changes**: Service methods now return `Result` objects

```python
# Old (v0.2.0)
project = await project_service.create_project("Title")

# New (v1.0.0)
result = await project_service.create_project("Title")
if result.is_ok():
    project = result.value
```

---

## [0.2.0] - 2025-XX-XX

### Added
- Initial release with basic novel rewriting functionality
- TXT file import and chapter splitting
- Simple AI-powered text rewriting
- Basic memory storage with SQLite

---

## Version History

| Version | Date | Description |
|:---|:---|:---|
| 1.0.0 | 2026-03-30 | Complete architecture refactoring with DDD |
| 0.2.0 | 2025-XX-XX | Initial beta release |
