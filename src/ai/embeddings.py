"""文本向量（Embedding）：本地中文模型或 OpenAI 兼容的 /embeddings 接口。

- 本地：ONNX 格式的 bge-small-zh-v1.5，首次使用时从 Hugging Face（可设置镜像）下载到数据目录，
  之后完全离线；只依赖 onnxruntime + tokenizers，不需要 PyTorch
- API：任何提供 /embeddings 的服务（OpenAI、硅基流动、Ollama 等）

向量都做了 L2 归一化，点积即余弦相似度。所有调用都是阻塞的，由向量记忆放到后台线程执行。
"""
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Protocol

import numpy as np

from src import paths

DEFAULT_LOCAL_MODEL = "Xenova/bge-small-zh-v1.5"
DEFAULT_MIRROR = "https://hf-mirror.com"
MIRRORS = {"https://hf-mirror.com": "hf-mirror.com（国内镜像）", "https://huggingface.co": "huggingface.co（官方）"}
DEFAULT_API_MODEL = "text-embedding-3-small"
MAX_TOKENS = 512
BATCH_SIZE = 32
# 不同服务的单条输入上限不同（bge-large-zh 只有 512 token）：统一截断，超长段落只取开头生成向量（原文照常保存）
MAX_API_INPUT_CHARS = 500
# 下载失败后这段时间内不再重试，直接报同样的错：导入一本书时每章都要生成向量，不能每章都等一次下载超时
DOWNLOAD_RETRY_SECONDS = 300
_download_lock = threading.Lock()  # 多个标签页同时首次使用本地模型时依次进行，后到的直接用已下载的文件


class EmbeddingError(Exception):
    """生成向量失败。消息面向用户。"""


class Embedder(Protocol):
    name: str  # 模型标识；换了模型的旧向量需要重新生成

    def embed(self, texts: list[str]) -> np.ndarray: ...


def normalize(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    with urllib.request.urlopen(url, timeout=60) as response, open(partial, "wb") as f:
        while chunk := response.read(1 << 20):
            f.write(chunk)
    partial.replace(target)  # 下载完整后才改名，中断不会留下损坏的文件


class LocalEmbedder:
    """本地 ONNX 句向量模型（BERT 结构）。pooling：bge 用 cls，MiniLM 等用 mean。"""

    def __init__(
        self,
        repo: str = DEFAULT_LOCAL_MODEL,
        mirror: str = DEFAULT_MIRROR,
        model_dir: Optional[Path] = None,
        model_file: str = "onnx/model_quantized.onnx",
        tokenizer_file: str = "tokenizer.json",
        pooling: str = "cls",
        download: Callable[[str, Path], None] = _download,
    ):
        self.repo, self.mirror = repo, (mirror or DEFAULT_MIRROR).rstrip("/")
        self.model_dir = Path(model_dir) if model_dir else paths.models_dir() / repo.replace("/", "--")
        self.model_file, self.tokenizer_file, self.pooling = model_file, tokenizer_file, pooling
        self._download = download
        self._session = self._tokenizer = None
        self._failed: Optional[tuple[float, str]] = None  # 最近一次下载失败的时间和提示
        self.name = f"local:{repo}"

    def _ensure_files(self) -> None:
        if self._failed and time.monotonic() - self._failed[0] < DOWNLOAD_RETRY_SECONDS:
            raise EmbeddingError(self._failed[1])
        with _download_lock:
            for rel in (self.tokenizer_file, self.model_file):
                target = self.model_dir / rel
                if target.exists():
                    continue
                url = f"{self.mirror}/{self.repo}/resolve/main/{rel}"
                try:
                    self._download(url, target)
                except Exception as error:
                    message = f"下载本地向量模型失败（{url}）：{error}。可在设置里更换下载镜像，或改用 API 生成向量"
                    self._failed = (time.monotonic(), message)
                    raise EmbeddingError(message) from error
        self._failed = None

    def _load(self) -> None:
        if self._session:
            return
        self._ensure_files()
        import onnxruntime
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(str(self.model_dir / self.tokenizer_file))
        tokenizer.enable_truncation(MAX_TOKENS)
        tokenizer.enable_padding()
        self._tokenizer = tokenizer
        self._session = onnxruntime.InferenceSession(
            str(self.model_dir / self.model_file), providers=["CPUExecutionProvider"])

    def embed(self, texts: list[str]) -> np.ndarray:
        self._load()
        wanted = {i.name for i in self._session.get_inputs()}
        batches = []
        for start in range(0, len(texts), BATCH_SIZE):
            encodings = self._tokenizer.encode_batch(texts[start:start + BATCH_SIZE])
            inputs = {
                "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
                "token_type_ids": np.array([e.type_ids for e in encodings], dtype=np.int64),
            }
            hidden = self._session.run(None, {k: v for k, v in inputs.items() if k in wanted})[0]
            if self.pooling == "cls":
                pooled = hidden[:, 0]
            else:
                mask = inputs["attention_mask"][..., None].astype(np.float32)
                pooled = (hidden * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1e-9)
            batches.append(pooled)
        return normalize(np.concatenate(batches)) if batches else np.zeros((0, 0), np.float32)


class ApiEmbedder:
    """OpenAI 兼容的 /embeddings 接口。"""

    def __init__(self, config: dict, http_client=None):
        from src.llm.client import needs_api_key, resolve_base_url

        self.config = config
        self.base_url = resolve_base_url(config)
        self.model = (config.get("model") or DEFAULT_API_MODEL).strip()
        self._needs_key = needs_api_key(config)
        self._http_client = http_client
        self._client = None
        self.name = f"api:{self.base_url.rstrip('/')}|{self.model}"

    def _get_client(self):
        if self._needs_key:
            raise EmbeddingError("向量 API 的 Key 未设置，请在设置的「记忆」页填写，或改用本地模型")
        if not self._client:
            import openai

            proxy = (self.config.get("proxy") or "").strip()
            http_client = self._http_client or (openai.DefaultHttpxClient(proxy=proxy) if proxy else None)
            self._client = openai.OpenAI(api_key=(self.config.get("api_key") or "").strip() or "local",
                                         base_url=self.base_url, http_client=http_client, max_retries=2)
        return self._client

    def embed(self, texts: list[str]) -> np.ndarray:
        import openai

        client = self._get_client()
        vectors = []
        try:
            for start in range(0, len(texts), BATCH_SIZE):
                batch = [t[:MAX_API_INPUT_CHARS] for t in texts[start:start + BATCH_SIZE]]
                response = client.embeddings.create(model=self.model, input=batch)
                data = sorted(response.data or [], key=lambda d: d.index)
                if [item.index for item in data] != list(range(len(batch))):
                    raise EmbeddingError(f"向量 API 返回的结果不完整（{self.base_url}，模型 {self.model}）："
                                         f"发送 {len(batch)} 条，收到 {len(data)} 条")
                vectors += [item.embedding for item in data]
        except (openai.OpenAIError, ValueError) as error:  # SDK 收到空结果时抛 ValueError
            raise EmbeddingError(f"向量 API 调用失败（{self.base_url}，模型 {self.model}）：{error}") from error
        if vectors and (len({len(v) for v in vectors}) != 1 or not vectors[0]):
            raise EmbeddingError(f"向量 API 返回的向量为空或维度不一致（{self.base_url}，模型 {self.model}）")
        return normalize(np.array(vectors)) if vectors else np.zeros((0, 0), np.float32)


# 提供 /embeddings 的常用服务：(名称, Base URL, 推荐模型)
API_PRESETS = [
    ("OpenAI", "https://api.openai.com/v1", "text-embedding-3-small"),
    ("硅基流动", "https://api.siliconflow.cn/v1", "BAAI/bge-m3"),
    ("Ollama（本地）", "http://localhost:11434/v1", "bge-m3"),
]


def check_embedder(config: dict) -> int:
    """按配置生成一条测试向量（本地模型会先下载），返回向量维度。失败时抛出 EmbeddingError。"""
    try:
        vectors = create_embedder(config).embed(["连接测试"])
    except EmbeddingError:
        raise
    except Exception as error:  # 模型文件损坏、推理出错等
        raise EmbeddingError(f"生成向量失败：{error}") from error
    return int(vectors.shape[1])


def create_embedder(config: dict) -> Embedder:
    """按设置里的 embedding 配置创建。"""
    if config.get("provider") == "api":
        return ApiEmbedder(config)
    return LocalEmbedder(repo=config.get("local_model") or DEFAULT_LOCAL_MODEL,
                         mirror=config.get("mirror") or DEFAULT_MIRROR)
