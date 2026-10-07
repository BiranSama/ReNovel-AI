"""精修流程：检索上下文 → Writer 改写 → Reviewer 审校 → 未达标时重试。

单段、全文、批量三种场景共用这一套流程，区别只在于：
- 是否有人在场（on_reject）：审校模式为 manual 时，由用户决定重试还是接受；
  没有人在场（批量）时总是按审校意见自动重试
- 是否附带额外写作建议（guidance，如全文模式的军师报告）
"""
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from src.llm import LLMError
from src.llm.prompts import assemble_system_prompt, join_sections, parse_json_object, section
from src.services.context import ContextBuilder


@dataclass
class RefineRequest:
    text: str
    instruction: str
    project_id: Optional[str] = None
    chapter_index: int = 0
    guidance: str = ""  # 额外写作建议，如军师报告
    persona: str = ""   # 角色卡人设，放在 Writer 系统提示词之前


@dataclass
class Review:
    score: Optional[float]
    suggestion: str
    passed: bool
    raw: str = ""
    error: str = ""  # 审校调用失败时的提示；此时不拦截改写结果


@dataclass
class RefineResult:
    text: str
    review: Optional[Review]
    attempts: int


# 审校未通过时询问用户：返回修改意见则据此重写，返回 None 表示接受当前结果
OnReject = Callable[[Review, str], Awaitable[Optional[str]]]
OnText = Callable[[str], None]


class RefinePipeline:
    def __init__(self, llm, settings, context: ContextBuilder):
        self.llm = llm
        self.settings = settings
        self.context = context

    async def refine(
        self,
        request: RefineRequest,
        on_text: Optional[OnText] = None,
        on_reject: Optional[OnReject] = None,
    ) -> RefineResult:
        """改写并按审校策略重试。Writer 调用失败时抛出 LLMError。"""
        reviewing = self.settings.is_reviewer_enabled()
        ask_user = on_reject is not None and self.settings.get_review_mode() == "manual"
        max_attempts = 1 + self.settings.get_max_review_retries() if reviewing else 1
        references = self.context.gather(request.project_id, request.text, request.chapter_index, "reader")

        feedback = ""
        attempts = 0
        while True:
            attempts += 1
            text = await self._write(request, references, feedback, on_text)
            if not reviewing:
                return RefineResult(text, None, attempts)

            review = await self.review(request, text)
            if review.passed or attempts >= max_attempts:
                return RefineResult(text, review, attempts)

            if ask_user:
                decision = await on_reject(review, text)
                if decision is None:
                    return RefineResult(text, review, attempts)
                feedback = decision
            else:
                feedback = review.suggestion

    async def review(self, request: RefineRequest, candidate: str) -> Review:
        """给改写结果打分。审校失败或无法解析时不拦截（passed=True），失败原因记在 error。"""
        references = self.context.gather(request.project_id, request.text, request.chapter_index, "author")
        prompt = join_sections(
            section("设定资料（作者视角）", references),
            section("原文", request.text),
            section("改写", candidate),
            section("改写指令", request.instruction),
            '请评分，只输出 JSON：{"score": 0 到 10 的整数, "suggestion": "具体修改建议"}',
        )
        try:
            raw = await self.llm.complete(self._role("reviewer"), self._messages("reviewer", prompt))
        except LLMError as error:
            return Review(score=None, suggestion="", passed=True, error=str(error))

        data = parse_json_object(raw) or {}
        try:
            score = float(data["score"])
        except (KeyError, TypeError, ValueError):
            return Review(score=None, suggestion=str(data.get("suggestion", "")), passed=True, raw=raw)
        passed = score >= self.settings.get_review_threshold()
        return Review(score=score, suggestion=str(data.get("suggestion", "")), passed=passed, raw=raw)

    async def analyze(self, request: RefineRequest) -> str:
        """军师分析：评估改写指令的可行性与风险，输出简报。"""
        references = self.context.gather(request.project_id, request.text, request.chapter_index, "author")
        prompt = join_sections(
            section("设定资料（作者视角）", references),
            section("改写指令", request.instruction),
            section("原文", request.text),
            "请输出简报：1. 可行性 2. 风险（OOC / 伏笔） 3. 建议",
        )
        return await self.llm.complete(self._role("analyzer"), self._messages("analyzer", prompt))

    async def _write(self, request: RefineRequest, references: str, feedback: str, on_text: Optional[OnText]) -> str:
        prompt = join_sections(
            section("参考资料", references),
            section("写作建议", request.guidance),
            section("审校意见（必须执行）", feedback),
            section("指令", request.instruction),
            section("原文", request.text),
            "请直接输出改写后的正文。",
        )
        messages = self._messages("writer", prompt, persona=request.persona)
        if on_text:
            on_text("")
        text = ""
        async for token in self.llm.stream(self._role("writer"), messages):
            text += token
            if on_text:
                on_text(text)
        return text

    def _role(self, role_key: str) -> dict:
        return self.settings.resolve_role(role_key)

    def _messages(self, role_key: str, prompt: str, persona: str = "") -> list[dict]:
        system = assemble_system_prompt(
            self.settings.get_role_config(role_key), self.settings.is_nsfw_enabled(), persona
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
