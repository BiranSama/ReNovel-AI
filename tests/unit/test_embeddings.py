"""向量模型：本地模型的下载与缓存、ONNX 推理（有缓存的模型时）、API 接口。不联网。"""
import json
import threading
import time
from pathlib import Path

import httpx2
import numpy as np
import openai
import pytest

from src.ai.embeddings import (DOWNLOAD_RETRY_SECONDS, MAX_API_INPUT_CHARS, ApiEmbedder, EmbeddingError,
                               LocalEmbedder, create_embedder)

CHROMA_MINILM = Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2" / "onnx"


def test_local_model_is_downloaded_once_from_mirror(tmp_path):
    fetched = []

    def download(url, target):
        fetched.append(url)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x")

    embedder = LocalEmbedder(repo="org/model", mirror="https://mirror.example.com/", model_dir=tmp_path, download=download)
    embedder._ensure_files()
    embedder._ensure_files()
    assert fetched == ["https://mirror.example.com/org/model/resolve/main/tokenizer.json",
                       "https://mirror.example.com/org/model/resolve/main/onnx/model_quantized.onnx"]
    assert embedder.name == "local:org/model"


def test_download_failure_is_reported_with_hint(tmp_path):
    def download(url, target):
        raise OSError("connection refused")

    with pytest.raises(EmbeddingError, match="更换下载镜像"):
        LocalEmbedder(model_dir=tmp_path, download=download).embed(["你好"])


def test_failed_download_is_not_retried_for_every_chapter(tmp_path, monkeypatch):
    """镜像连不上时，导入一本书的每一章都要生成向量：失败后一段时间内直接报错，不再每章等一次下载超时。"""
    attempts = []

    def download(url, target):
        attempts.append(url)
        raise OSError("timed out")

    embedder = LocalEmbedder(model_dir=tmp_path, download=download)
    for _ in range(3):
        with pytest.raises(EmbeddingError, match="timed out"):
            embedder.embed(["你好"])
    assert len(attempts) == 1

    later = time.monotonic() + DOWNLOAD_RETRY_SECONDS + 1
    monkeypatch.setattr("src.ai.embeddings.time.monotonic", lambda: later)
    with pytest.raises(EmbeddingError):
        embedder.embed(["你好"])
    assert len(attempts) == 2  # 过了这段时间再试（换镜像会新建实例，立即重试）


def test_concurrent_first_use_downloads_each_file_once(tmp_path):
    """两个标签页同时首次使用本地模型：依次下载，不会同时写同一个临时文件。"""
    fetched, active = [], []

    def download(url, target):
        assert not active, "两个下载同时进行"
        active.append(url)
        time.sleep(0.05)
        fetched.append(url)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x")
        active.pop()

    embedders = [LocalEmbedder(model_dir=tmp_path, download=download) for _ in range(2)]
    threads = [threading.Thread(target=e._ensure_files) for e in embedders]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(fetched) == 2  # 分词器和模型各一次


@pytest.mark.skipif(not (CHROMA_MINILM / "model.onnx").exists(), reason="本机没有缓存的 ONNX 模型")
def test_onnx_inference_with_cached_model():
    embedder = LocalEmbedder(model_dir=CHROMA_MINILM, model_file="model.onnx", pooling="mean",
                             download=lambda *a: pytest.fail("不应下载"))
    vectors = embedder.embed(["The cat sits on the mat.", "A cat is sitting on a mat.", "Stock prices fell sharply."])
    assert vectors.shape == (3, 384)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
    similar, different = vectors[0] @ vectors[1], vectors[0] @ vectors[2]
    assert similar > different + 0.3


def api_embedder(respond, **config):
    requests = []

    def handler(request):
        requests.append(request)
        return respond(request)

    conf = {"api_key": "sk-test", "base_url": "https://emb.example.com/v1", "model": "bge-m3", **config}
    client = openai.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    return ApiEmbedder(conf, http_client=client), requests


def test_api_embedder_batches_and_normalizes():
    def respond(request):
        texts = json.loads(request.content)["input"]
        data = [{"object": "embedding", "index": i, "embedding": [3.0, 4.0]} for i in reversed(range(len(texts)))]
        return httpx2.Response(200, json={"object": "list", "data": data, "model": "bge-m3",
                                          "usage": {"prompt_tokens": 1, "total_tokens": 1}})

    embedder, requests = api_embedder(respond)
    vectors = embedder.embed([f"第{i}段" for i in range(40)])
    assert vectors.shape == (40, 2) and np.allclose(vectors[0], [0.6, 0.8])
    assert [len(json.loads(r.content)["input"]) for r in requests] == [32, 8]
    assert str(requests[0].url) == "https://emb.example.com/v1/embeddings"
    assert embedder.name == "api:https://emb.example.com/v1|bge-m3"


def test_api_embedder_errors_are_friendly():
    embedder, _ = api_embedder(lambda r: httpx2.Response(401, json={"error": {"message": "bad key"}}))
    with pytest.raises(EmbeddingError, match="向量 API 调用失败"):
        embedder.embed(["你好"])

    no_key, _ = api_embedder(lambda r: pytest.fail("不应发请求"), api_key="")
    with pytest.raises(EmbeddingError, match="Key 未设置"):
        no_key.embed(["你好"])


def test_create_embedder_from_settings():
    assert isinstance(create_embedder({"provider": "local"}), LocalEmbedder)
    assert isinstance(create_embedder({}), LocalEmbedder)
    api = create_embedder({"provider": "api", "base_url": "http://localhost:11434/v1", "model": "bge-m3"})
    assert isinstance(api, ApiEmbedder) and api.name == "api:http://localhost:11434/v1|bge-m3"


def test_api_inputs_are_truncated():
    def respond(request):
        texts = json.loads(request.content)["input"]
        data = [{"object": "embedding", "index": i, "embedding": [1.0, 0.0]} for i in range(len(texts))]
        return httpx2.Response(200, json={"object": "list", "data": data, "model": "m",
                                          "usage": {"prompt_tokens": 1, "total_tokens": 1}})

    embedder, requests = api_embedder(respond)
    embedder.embed(["长" * 5000, "短"])
    assert [len(t) for t in json.loads(requests[0].content)["input"]] == [MAX_API_INPUT_CHARS, 1]


@pytest.mark.parametrize("data", [
    [],                                                       # 成功但没有结果
    [{"index": 0, "embedding": [1.0, 0.0]}],                  # 少了一条
    [{"index": 0, "embedding": [1.0, 0.0]}, {"index": 1, "embedding": [1.0]}],  # 维度不一致
])
def test_incomplete_api_response_is_an_error(data):
    """兼容接口返回的结果不完整时报错，而不是把条数不对的向量存进去（之后会反复补算或越界）。"""
    def respond(request):
        items = [{"object": "embedding", **item} for item in data]
        return httpx2.Response(200, json={"object": "list", "data": items, "model": "m",
                                          "usage": {"prompt_tokens": 1, "total_tokens": 1}})

    embedder, _ = api_embedder(respond)
    with pytest.raises(EmbeddingError, match="向量 API"):
        embedder.embed(["甲", "乙"])
