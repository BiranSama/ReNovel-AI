# Re:Novel AI 重构框架

## 一、项目目录结构

```
ReNovel-AI/
├── main.py                          # 应用入口
├── requirements.txt                 # 依赖清单
├── pyproject.toml                   # 项目配置 (新增)
│
├── config/                          # 配置层 (新增)
│   ├── __init__.py
│   ├── settings.py                  # 全局配置
│   └── prompts/                     # Prompt 模板
│       ├── writer.yaml
│       ├── reviewer.yaml
│       ├── analyzer.yaml
│       └── chat.yaml
│
├── src/
│   ├── __init__.py
│   │
│   ├── domain/                      # 领域层 (新增)
│   │   ├── __init__.py
│   │   ├── entities/                # 实体定义
│   │   │   ├── __init__.py
│   │   │   ├── project.py
│   │   │   ├── chapter.py
│   │   │   ├── segment.py
│   │   │   ├── character.py
│   │   │   └── relation.py
│   │   ├── value_objects/           # 值对象
│   │   │   ├── __init__.py
│   │   │   └── config.py
│   │   └── events/                  # 领域事件
│   │       ├── __init__.py
│   │       └── events.py
│   │
│   ├── application/                 # 应用层 (新增)
│   │   ├── __init__.py
│   │   ├── services/                # 应用服务
│   │   │   ├── __init__.py
│   │   │   ├── project_service.py
│   │   │   ├── chapter_service.py
│   │   │   ├── rewrite_service.py
│   │   │   ├── batch_service.py
│   │   │   ├── chat_service.py
│   │   │   ├── import_service.py
│   │   │   └── graph_service.py
│   │   ├── use_cases/               # 用例
│   │   │   ├── __init__.py
│   │   │   ├── rewrite_chapter.py
│   │   │   ├── batch_rewrite.py
│   │   │   └── build_graph.py
│   │   └── dto/                     # 数据传输对象
│   │       ├── __init__.py
│   │       └── requests.py
│   │
│   ├── infrastructure/              # 基础设施层 (重构)
│   │   ├── __init__.py
│   │   ├── database/                # 数据库
│   │   │   ├── __init__.py
│   │   │   ├── connection.py
│   │   │   ├── migrations/          # 数据库迁移
│   │   │   │   └── init_schema.sql
│   │   │   └── repositories/        # 仓储实现
│   │   │       ├── __init__.py
│   │   │       ├── project_repo.py
│   │   │       ├── chapter_repo.py
│   │   │       └── graph_repo.py
│   │   ├── llm/                     # LLM 基础设施
│   │   │   ├── __init__.py
│   │   │   ├── gateway.py           # LLM 网关
│   │   │   ├── providers/           # 提供商适配器
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   ├── openai_provider.py
│   │   │   │   ├── google_provider.py
│   │   │   │   └── local_provider.py
│   │   │   ├── rate_limiter.py      # 速率限制
│   │   │   ├── circuit_breaker.py   # 熔断器
│   │   │   └── token_counter.py     # Token 计数
│   │   ├── rag/                     # RAG 基础设施
│   │   │   ├── __init__.py
│   │   │   ├── pipeline.py          # RAG 管道
│   │   │   ├── embedders/           # 嵌入器
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   ├── openai_embedder.py
│   │   │   │   └── local_embedder.py
│   │   │   ├── chunkers/            # 分块器
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   └── novel_chunker.py
│   │   │   ├── retrievers/          # 检索器
│   │   │   │   ├── __init__.py
│   │   │   │   ├── hybrid.py
│   │   │   │   └── reranker.py
│   │   │   └── vector_stores/       # 向量存储
│   │   │       ├── __init__.py
│   │   │       └── chromadb_store.py
│   │   ├── graph/                   # 知识图谱
│   │   │   ├── __init__.py
│   │   │   ├── engine.py
│   │   │   ├── extractor.py
│   │   │   └── disambiguator.py
│   │   ├── parsers/                 # 解析器
│   │   │   ├── __init__.py
│   │   │   ├── tavern_parser.py
│   │   │   └── novel_parser.py
│   │   └── cache/                   # 缓存
│   │       ├── __init__.py
│   │       └── redis_cache.py
│   │
│   ├── interfaces/                  # 接口层 (重构)
│   │   ├── __init__.py
│   │   ├── web/                     # Web 接口
│   │   │   ├── __init__.py
│   │   │   ├── app.py               # NiceGUI 应用
│   │   │   ├── routes/              # 路由 (可选 API)
│   │   │   │   └── __init__.py
│   │   │   └── middleware/          # 中间件
│   │   │       └── __init__.py
│   │   ├── view_models/             # 视图模型
│   │   │   ├── __init__.py
│   │   │   ├── editor_vm.py
│   │   │   ├── project_vm.py
│   │   │   ├── settings_vm.py
│   │   │   └── graph_vm.py
│   │   ├── controllers/             # 控制器
│   │   │   ├── __init__.py
│   │   │   ├── editor_controller.py
│   │   │   ├── project_controller.py
│   │   │   └── batch_controller.py
│   │   └── views/                   # 视图组件
│   │       ├── __init__.py
│   │       ├── components/          # UI 组件
│   │       │   ├── __init__.py
│   │       │   ├── editor.py
│   │       │   ├── sidebar.py
│   │       │   ├── header.py
│   │       │   ├── chat_panel.py
│   │       │   ├── graph_view.py
│   │       │   └── settings_dialog.py
│   │       └── layouts/             # 布局
│   │           ├── __init__.py
│   │           └── main_layout.py
│   │
│   ├── shared/                      # 共享模块 (新增)
│   │   ├── __init__.py
│   │   ├── types.py                 # 类型定义
│   │   ├── exceptions.py            # 异常定义
│   │   ├── result.py                # Result 模式
│   │   ├── events.py                # 事件总线
│   │   └── utils/                   # 工具函数
│   │       ├── __init__.py
│   │       ├── logger.py
│   │       ├── text.py
│   │       └── json.py
│   │
│   └── di/                          # 依赖注入 (新增)
│       ├── __init__.py
│       └── container.py
│
├── data/                            # 数据目录
│   ├── projects/                    # SQLite 数据库
│   ├── vectordb/                    # 向量数据库
│   ├── config/                      # 用户配置
│   └── presets/                     # 预设文件
│
└── tests/                           # 测试目录 (新增)
    ├── __init__.py
    ├── unit/                        # 单元测试
    │   ├── __init__.py
    │   ├── test_services/
    │   └── test_repositories/
    ├── integration/                 # 集成测试
    │   └── __init__.py
    └── fixtures/                    # 测试数据
        └── sample_novel.txt
```

## 二、模块依赖关系

```
┌─────────────────────────────────────────────────────────────────┐
│                        Interfaces Layer                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Views     │  │ ViewModels  │  │     Controllers         │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘  │
└─────────┼────────────────┼─────────────────────┼────────────────┘
          │                │                     │
          ▼                ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Application Layer                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Services   │  │  Use Cases  │  │         DTOs            │  │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────────────┘  │
└─────────┼────────────────┼──────────────────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Domain Layer                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Entities   │  │Value Objects│  │       Events            │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
          ▲                ▲
          │                │
┌─────────┴────────────────┴──────────────────────────────────────┐
│                     Infrastructure Layer                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │Database  │ │   LLM    │ │   RAG    │ │  Graph   │           │
│  │Repos     │ │ Gateway  │ │ Pipeline │ │ Engine   │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

## 三、核心接口定义

### 3.1 仓储接口

```python
class ProjectRepository(Protocol):
    async def save(self, project: Project) -> Project: ...
    async def find_by_id(self, project_id: str) -> Optional[Project]: ...
    async def find_all(self, limit: int = 100) -> list[Project]: ...
    async def delete(self, project_id: str) -> bool: ...

class ChapterRepository(Protocol):
    async def save(self, chapter: Chapter) -> Chapter: ...
    async def find_by_id(self, chapter_id: str) -> Optional[Chapter]: ...
    async def find_by_project(self, project_id: str) -> list[Chapter]: ...
    async def update_content(self, chapter_id: str, content: str) -> bool: ...
```

### 3.2 LLM 网关接口

```python
class LLMGateway(Protocol):
    async def invoke(self, request: LLMRequest) -> LLMResponse: ...
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]: ...
```

### 3.3 RAG 管道接口

```python
class RAGPipeline(Protocol):
    async def index(self, project_id: str, chapter_id: str, text: str) -> int: ...
    async def retrieve(self, query: str, project_id: str, top_k: int) -> RetrievalResult: ...
```

## 四、重构任务清单

### Phase 1: 基础架构 (Week 1-2)

| 任务 | 优先级 | 状态 |
|------|--------|------|
| 创建 domain 层实体定义 | P0 | 待开始 |
| 创建 shared 类型定义 | P0 | 待开始 |
| 创建基础设施层接口 | P0 | 待开始 |
| 重构 LLM 客户端为 Gateway | P0 | 待开始 |
| 重构 RAG 为 Pipeline 模式 | P0 | 待开始 |

### Phase 2: 服务层 (Week 3-4)

| 任务 | 优先级 | 状态 |
|------|--------|------|
| 创建 Application 服务 | P0 | 待开始 |
| 创建 ViewModels | P1 | 待开始 |
| 创建 Controllers | P1 | 待开始 |
| 重构 handlers.py | P0 | 待开始 |

### Phase 3: UI 层 (Week 5-6)

| 任务 | 优先级 | 状态 |
|------|--------|------|
| 重构 UI 组件 | P1 | 待开始 |
| 实现响应式状态管理 | P1 | 待开始 |
| 添加错误处理 UI | P2 | 待开始 |

### Phase 4: 测试与优化 (Week 7-8)

| 任务 | 优先级 | 状态 |
|------|--------|------|
| 添加单元测试 | P1 | 待开始 |
| 添加集成测试 | P2 | 待开始 |
| 性能优化 | P2 | 待开始 |

## 五、命名约定

### 文件命名
- 模块文件: `snake_case.py`
- 类文件: 与主类同名 `snake_case.py`
- 测试文件: `test_<module>.py`

### 类命名
- 实体: 名词 `Project`, `Chapter`
- 值对象: 名词 `Config`, `Segment`
- 服务: 动词+名词 `RewriteService`
- 仓储: 名词+Repository `ProjectRepository`
- 控制器: 名词+Controller `EditorController`
- 视图模型: 名词+ViewModel `EditorViewModel`

### 方法命名
- 查询: `get_`, `find_`, `list_`
- 命令: `create_`, `update_`, `delete_`, `save_`
- 布尔: `is_`, `has_`, `can_`, `should_`
