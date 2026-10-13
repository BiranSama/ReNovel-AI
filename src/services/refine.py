"""精修流程：检索上下文 → Writer 改写 → Reviewer 审校 → 未达标时重试。

单段、全文、批量三种场景共用这一套流程，区别只在于：
- 是否有人在场（on_reject）：审校模式为 manual 时，由用户决定重试还是接受；
  没有人在场（批量）时总是按审校意见自动重试
- 是否附带额外写作建议（guidance，如全文模式的军师报告）
"""
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from src.llm import LLMError
from src.llm.prompts import assemble_system_prompt, join_sections, parse_json_object, section
from src.services.context import ContextBuilder

# Reviewer 同时读原文和改写，各取前后两部分，避免全文模式下超出模型上下文
REVIEW_EXCERPT_CHARS = 6000
REVIEW_INSTRUCTION = (
    "请评分，并对照设定资料检查改写：人物言行是否符合角色档案（OOC）、与前文事件和角色状态是否矛盾（时间线）、"
    "是否提前泄露了伏笔，以及是否完成改写指令。冲突要指出具体出处，如“第3章张三左臂受伤，此处却用左手提剑”。\n"
    '只输出 JSON：{"score": 0 到 10 的整数, "suggestion": "具体修改建议", "conflicts": ["具体冲突，没有则为空列表"]}'
)
STYLE_REVIEW_INSTRUCTION = (
    "另外对照文风档案给出文风贴合度（0 到 10 的整数），总分也要考虑文风是否贴合。"
    '在 JSON 里加上 "style_score" 字段。'
)
MAX_STYLE_SAMPLES = 3  # 与 src.services.style.MAX_SAMPLES 一致


def excerpt(text: str, limit: int = REVIEW_EXCERPT_CHARS) -> str:
    """超长文本保留开头和结尾，中间用省略标记代替。"""
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n……（中间省略 {len(text) - 2 * half} 字）……\n{text[-half:]}"


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
    conflicts: list[str] = field(default_factory=list)  # 与前文设定的具体冲突（OOC、时间线、伏笔）
    style_score: Optional[float] = None  # 文风贴合度（有文风档案时才评）

    @property
    def feedback(self) -> str:
        """交给 Writer 重写的意见：修改建议 + 具体冲突。"""
        lines = [self.suggestion] if self.suggestion else []
        lines += [f"冲突：{c}" for c in self.conflicts]
        return "\n".join(lines)


@dataclass
class RefineResult:
    text: str
    review: Optional[Review]
    attempts: int


def _number(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def style_samples(style) -> str:
    samples = [s for s in (style.samples if style else []) if s.strip()][:MAX_STYLE_SAMPLES]
    return "\n".join(f"- {s}" for s in samples)


def style_text(style) -> str:
    """给 Reviewer 看的文风档案：描述 + 示例段落。"""
    if not style:
        return ""
    samples = style_samples(style)
    return style.description + (f"\n示例：\n{samples}" if samples else "")


def parse_review(raw: str, threshold: float, with_style: bool = False) -> Review:
    data = parse_json_object(raw) or {}
    suggestion = str(data.get("suggestion", ""))
    conflicts = data.get("conflicts") if isinstance(data.get("conflicts"), list) else []
    conflicts = [str(c).strip() for c in conflicts if str(c).strip()]
    style_score = _number(data.get("style_score")) if with_style else None
    score = _number(data.get("score"))
    if score is None:  # 无法解析：不拦截
        return Review(score=None, suggestion=suggestion, passed=True, raw=raw, conflicts=conflicts,
                      style_score=style_score)
    return Review(score=score, suggestion=suggestion, passed=score >= threshold, raw=raw, conflicts=conflicts,
                  style_score=style_score)


async def write_with_review(settings, write, review, on_reject=None) -> "RefineResult":
    """写作 → 审校 → 未通过时重试，改写与续写共用。

    write(feedback) 返回正文，feedback 为空表示第一次；review(text) 返回 Review。
    on_reject 不为空且审校模式为 manual 时由用户决定重试还是接受，否则按审校意见自动重试。
    """
    reviewing = settings.is_reviewer_enabled()
    ask_user = on_reject is not None and settings.get_review_mode() == "manual"
    max_attempts = 1 + settings.get_max_review_retries() if reviewing else 1
    feedback = ""
    attempts = 0
    while True:
        attempts += 1
        text = await write(feedback)
        if not reviewing:
            return RefineResult(text, None, attempts)

        result = await review(text)
        if result.passed:
            return RefineResult(text, result, attempts)

        can_retry = attempts < max_attempts
        if ask_user:  # 最后一次仍未通过也要让用户看到审校意见，再决定是否接受
            decision = await on_reject(result, text, can_retry)
            if decision is None or not can_retry:
                return RefineResult(text, result, attempts)
            feedback = decision
        elif not can_retry:
            return RefineResult(text, result, attempts)
        else:
            feedback = result.feedback


_LOAD = object()  # review() 的 style 参数缺省值：读取当前的文风档案


# 审校未通过时询问用户：返回修改意见则据此重写，返回 None 表示接受当前结果。
# 第三个参数 can_retry 为 False 表示已达最多重试次数，这次询问只能接受当前结果
OnReject = Callable[[Review, str, bool], Awaitable[Optional[str]]]
OnText = Callable[[str], None]


class RefinePipeline:
    def __init__(self, llm, settings, context: ContextBuilder, styles=None):
        self.llm = llm
        self.settings = settings
        self.context = context
        self.styles = styles  # StyleStore，可选；每次改写都重新读取，编辑档案后立即生效

    async def style_for(self, project_id):
        profile = await self.styles.get(project_id) if self.styles else None
        return profile if profile and not profile.is_empty else None

    async def refine(
        self,
        request: RefineRequest,
        on_text: Optional[OnText] = None,
        on_reject: Optional[OnReject] = None,
    ) -> RefineResult:
        """改写并按审校策略重试。Writer 调用失败时抛出 LLMError。"""
        references = await self.context.gather(request.project_id, request.text, request.chapter_index, "reader")
        snapshot = {}

        async def write(feedback):
            # 每次尝试都重新读取文风档案，写与审用同一份（重试期间档案被修改也不会前后不一致）
            snapshot["style"] = await self.style_for(request.project_id)
            return await self._write(request, references, feedback, on_text, snapshot["style"])

        return await write_with_review(
            self.settings, write, lambda text: self.review(request, text, snapshot["style"]), on_reject)

    async def review(self, request: RefineRequest, candidate: str, style=_LOAD) -> Review:
        """给改写结果打分。审校失败或无法解析时不拦截（passed=True），失败原因记在 error。

        style 为写这一稿时用的文风档案；不传时读取当前的档案。
        """
        # 按原文和改写一起找资料：改写里新出现（或换成）的角色也要对照档案与前文事件
        references = await self.context.gather(request.project_id, f"{request.text}\n{candidate}",
                                               request.chapter_index, "author")
        if style is _LOAD:
            style = await self.style_for(request.project_id)
        prompt = join_sections(
            section("设定资料（作者视角）", references),
            section("文风档案", style_text(style)),
            section("原文", excerpt(request.text)),
            section("改写", excerpt(candidate)),
            section("改写指令", request.instruction),
            REVIEW_INSTRUCTION,
            STYLE_REVIEW_INSTRUCTION if style else "",
        )
        return await self.ask_reviewer(prompt, with_style=bool(style))

    async def ask_reviewer(self, prompt: str, with_style: bool = False) -> Review:
        """调用 Reviewer 并解析评分。调用失败或无法解析时不拦截（passed=True），失败原因记在 error。"""
        try:
            raw = await self.llm.complete(self._role("reviewer"), self._messages("reviewer", prompt))
        except LLMError as error:
            return Review(score=None, suggestion="", passed=True, error=str(error))
        return parse_review(raw, self.settings.get_review_threshold(), with_style)

    async def analyze(self, request: RefineRequest) -> str:
        """军师分析：评估改写指令的可行性与风险，输出简报。"""
        references = await self.context.gather(request.project_id, request.text, request.chapter_index, "author")
        prompt = join_sections(
            section("设定资料（作者视角）", references),
            section("改写指令", request.instruction),
            section("原文", request.text),
            "请输出简报：1. 可行性 2. 风险（OOC / 伏笔） 3. 建议",
        )
        return await self.llm.complete(self._role("analyzer"), self._messages("analyzer", prompt))

    async def _write(self, request: RefineRequest, references: str, feedback: str, on_text: Optional[OnText],
                     style=None) -> str:
        prompt = join_sections(
            section("参考资料", references),
            section("文风要求", style.description if style else ""),
            section("文风示例（学习语感，不要照抄内容）", style_samples(style)),
            section("写作建议", request.guidance),
            section("审校意见（必须执行）", feedback),
            section("指令", request.instruction),
            section("原文", request.text),
            "请直接输出改写后的正文。",
        )
        return await self.stream_writer(prompt, request.persona, on_text)

    async def stream_writer(self, prompt: str, persona: str = "", on_text: Optional[OnText] = None) -> str:
        """调用 Writer 流式生成，on_text 收到累计的文字。失败时抛出 LLMError。"""
        messages = self._messages("writer", prompt, persona=persona)
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
