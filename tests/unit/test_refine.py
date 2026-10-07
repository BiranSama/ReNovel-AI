"""统一精修流程：Writer → Reviewer → 重试策略。用假的 LLM 和记忆，不联网。"""
import asyncio

import pytest

from src.core.settings import AppSettings
from src.llm import LLMError
from src.services.context import ContextBuilder
from src.services.refine import RefinePipeline, RefineRequest

ROLES = ("writer", "reviewer", "analyzer")


class StubConfigManager:
    def __init__(self, config):
        self.config = config

    def load_config(self):
        return self.config

    def save_config(self, config):
        self.config = config


def make_settings(**overrides) -> AppSettings:
    config = {role: {"api_key": "k", "model": role, "base_url": "https://x/v1"} for role in ROLES}
    config.update({"enable_reviewer": True, "review_threshold": 8, "review_mode": "auto", "max_review_retries": 2})
    config.update(overrides)
    return AppSettings(StubConfigManager(config))


class FakeLLM:
    """按角色（配置里的 model 字段）返回预设输出，并记录每次调用的消息。"""

    def __init__(self, reviews=('{"score": 9, "suggestion": "好"}',), analysis="简报"):
        self.reviews = list(reviews)
        self.analysis = analysis
        self.calls: list[tuple[str, list[dict]]] = []
        self.writes = 0

    async def stream(self, config, messages):
        self.calls.append((config["model"], messages))
        self.writes += 1
        for piece in (f"改写{self.writes}", "。"):
            yield piece

    async def complete(self, config, messages):
        self.calls.append((config["model"], messages))
        if config["model"] == "reviewer":
            review = self.reviews.pop(0) if len(self.reviews) > 1 else self.reviews[0]
            if isinstance(review, Exception):
                raise review
            return review
        return self.analysis

    def prompts(self, role):
        return [messages[-1]["content"] for r, messages in self.calls if r == role]


class FakeMemory:
    def __init__(self):
        self.views = []

    def search(self, query, project_id, n_results=5):
        return ["张三走进咖啡馆。", "李四早已等候多时。"]


class FakeGraph:
    def context_for_text(self, text, current_chapter, mode="reader"):
        return "- 张三 朋友 李四" if mode == "reader" else "- 张三 朋友 李四\n- 张三 生父 王五 [🔒伏笔]"


def make_pipeline(llm, settings=None):
    context = ContextBuilder(FakeMemory(), lambda: FakeGraph())
    return RefinePipeline(llm, settings or make_settings(), context)


REQUEST = RefineRequest(text="张三走进咖啡馆。", instruction="润色", project_id="p1", chapter_index=3)


def run(pipeline, request=REQUEST, **kwargs):
    return asyncio.run(pipeline.refine(request, **kwargs))


def test_without_reviewer_writes_once():
    llm = FakeLLM()
    result = run(make_pipeline(llm, make_settings(enable_reviewer=False)))
    assert (result.text, result.review, result.attempts) == ("改写1。", None, 1)
    assert [role for role, _ in llm.calls] == ["writer"]


def test_writer_prompt_layout():
    llm = FakeLLM()
    run(make_pipeline(llm, make_settings(enable_reviewer=False)),
        RefineRequest(text="张三走进咖啡馆。", instruction="润色", project_id="p1", guidance="多写细节", persona="你是赛博侦探"))
    system, user = (m["content"] for m in llm.calls[0][1])
    assert system.startswith("你是赛博侦探\n### Role")
    assert "【相关记忆】\n- 李四早已等候多时。" in user
    assert "张三走进咖啡馆。" not in user.split("【原文】")[0]  # 原文本身不会被当作“记忆”
    assert "【人物关系】\n- 张三 朋友 李四" in user and "🔒" not in user  # Writer 只用读者视角
    assert "【写作建议】\n多写细节" in user
    assert user.count("张三走进咖啡馆。") == 1  # 原文只出现一次
    assert "审校意见" not in user


def test_on_text_streams_accumulated_text_and_resets_per_attempt():
    seen = []
    run(make_pipeline(FakeLLM(reviews=['{"score": 2, "suggestion": "改"}', '{"score": 9}'])), on_text=seen.append)
    assert seen == ["", "改写1", "改写1。", "", "改写2", "改写2。"]


def test_review_pass_returns_first_attempt():
    llm = FakeLLM()
    result = run(make_pipeline(llm))
    assert result.attempts == 1 and result.review.passed and result.review.score == 9
    review_prompt = llm.prompts("reviewer")[0]
    assert "🔒伏笔" in review_prompt  # Reviewer 用作者视角
    assert "【改写】\n改写1。" in review_prompt


def test_auto_retry_feeds_reviewer_suggestion_until_limit():
    llm = FakeLLM(reviews=['{"score": 3, "suggestion": "删掉形容词"}'])
    result = run(make_pipeline(llm))
    assert result.attempts == 3  # 1 次 + max_review_retries 次
    assert result.text == "改写3。" and not result.review.passed
    assert "【审校意见（必须执行）】\n删掉形容词" in llm.prompts("writer")[1]


def test_auto_retry_stops_once_review_passes():
    llm = FakeLLM(reviews=['{"score": 3, "suggestion": "改"}', '{"score": 8}'])
    result = run(make_pipeline(llm))
    assert result.attempts == 2 and result.review.passed and result.text == "改写2。"


def test_manual_mode_asks_user_and_uses_their_feedback():
    asked = []

    async def on_reject(review, text):
        asked.append((review.score, text))
        return "让对白更幽默"

    llm = FakeLLM(reviews=['{"score": 3, "suggestion": "改"}', '{"score": 9}'])
    result = run(make_pipeline(llm, make_settings(review_mode="manual")), on_reject=on_reject)
    assert asked == [(3.0, "改写1。")]
    assert result.attempts == 2
    assert "让对白更幽默" in llm.prompts("writer")[1]


def test_manual_mode_accepting_keeps_current_text():
    async def accept(review, text):
        return None

    llm = FakeLLM(reviews=['{"score": 3, "suggestion": "改"}'])
    result = run(make_pipeline(llm, make_settings(review_mode="manual")), on_reject=accept)
    assert (result.text, result.attempts, result.review.passed) == ("改写1。", 1, False)


def test_auto_mode_never_asks_user():
    async def fail(review, text):
        raise AssertionError("auto 模式不应询问用户")

    result = run(make_pipeline(FakeLLM(reviews=['{"score": 3}', '{"score": 9}'])), on_reject=fail)
    assert result.attempts == 2


@pytest.mark.parametrize("raw", ["看起来不错", '{"suggestion": "无分数"}', '{"score": "高"}'])
def test_unparseable_review_does_not_block(raw):
    result = run(make_pipeline(FakeLLM(reviews=[raw])))
    assert result.attempts == 1 and result.review.passed and result.review.score is None


def test_reviewer_failure_keeps_text_and_reports_error():
    result = run(make_pipeline(FakeLLM(reviews=[LLMError("额度不足")])))
    assert result.text == "改写1。"
    assert result.review.passed and result.review.error == "额度不足"


def test_writer_failure_propagates():
    class BrokenLLM(FakeLLM):
        async def stream(self, config, messages):
            raise LLMError("API Key 无效")
            yield  # pragma: no cover

    with pytest.raises(LLMError, match="API Key 无效"):
        run(make_pipeline(BrokenLLM()))


def test_analyze_uses_analyzer_role_and_author_view():
    llm = FakeLLM(analysis="1. 可行")
    assert asyncio.run(make_pipeline(llm).analyze(REQUEST)) == "1. 可行"
    role, messages = llm.calls[0]
    assert role == "analyzer"
    assert "🔒伏笔" in messages[-1]["content"]


def test_roles_without_key_inherit_writer_connection():
    settings = make_settings(reviewer={"api_key": "", "model": "reviewer", "temperature": 0.1,
                                       "prompt_blocks": {"persona": "总监"}})
    conf = settings.resolve_role("reviewer")
    assert (conf["api_key"], conf["model"], conf["base_url"]) == ("k", "writer", "https://x/v1")
    assert conf["temperature"] == 0.1 and conf["prompt_blocks"]["persona"] == "总监"  # 保留自己的提示词
    assert settings.get_role_config("reviewer")["api_key"] == ""  # 不改动原设置


def test_local_role_without_key_keeps_its_own_connection():
    settings = make_settings(chat={"api_key": "", "model": "qwen", "base_url": "http://localhost:11434/v1"})
    assert settings.resolve_role("chat")["model"] == "qwen"
