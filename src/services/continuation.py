"""续写：在全书末尾写新章节，或在章节中某段之后续写若干段。

- Writer 用读者视角的参考资料（前情提要、前文片段、角色截至此处的状态、已揭示的关系）、
  前文埋下的伏笔、文风档案，以及可选的大纲 / 走向
- Reviewer 用作者视角检查与前文的一致性、与后文的衔接、是否按大纲推进，以及文风；未通过时按审校策略重试
- 结果是草稿：采纳后才写入项目（新章节或插入段落），并进入向量记忆；章节记忆与图谱由调用方随后更新
"""
from dataclasses import dataclass
from typing import Optional

from src.llm.prompts import join_sections, section
from src.services.refine import (STYLE_REVIEW_INSTRUCTION, OnReject, OnText, RefinePipeline, RefineResult,
                                 excerpt, style_samples, style_text, write_with_review)

PRECEDING_CHARS = 1500  # 续写位置之前取多少字作为「前文」
FOLLOWING_CHARS = 300   # 段后续写时，之后的正文取多少字用来衔接
MAX_HOOKS = 8
LENGTHS = {300: "约 300 字（一两段）", 800: "约 800 字", 2000: "约 2000 字（一章的篇幅）"}
CONTINUE_REVIEW_INSTRUCTION = (
    "请评分，并对照设定资料检查续写：人物言行是否符合角色档案（OOC）、与前文事件和角色状态是否矛盾（时间线）、"
    "是否与前文自然衔接（有后文时还要能接上后文）、是否按大纲推进、伏笔的呼应是否合理。冲突要指出具体出处。\n"
    '只输出 JSON：{"score": 0 到 10 的整数, "suggestion": "具体修改建议", "conflicts": ["具体冲突，没有则为空列表"]}'
)


@dataclass
class ContinueRequest:
    project_id: str
    chapter_index: int     # 续写所在章节的序号（从 1 开始）；全书末尾续写新章节时为现有章节数 + 1
    preceding: str         # 续写位置之前的正文（新章节时为上一章的正文）
    following: str = ""    # 段后续写时，续写位置之后的正文
    outline: str = ""      # 大纲 / 走向，可选
    target_chars: int = 800
    title: str = ""        # 新章节的标题
    persona: str = ""


def tail(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else "……" + text[-limit:]


def head(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "……"


class ContinuationService:
    def __init__(self, pipeline: RefinePipeline, projects, rag=None, chapter_store=None):
        self.pipeline = pipeline            # 复用其上下文、文风、Writer 与 Reviewer
        self.projects = projects            # ProjectManager
        self.rag = rag                      # RAGEngine，可选：采纳后写入向量记忆
        self.chapter_store = chapter_store  # ChapterMemoryStore，可选：读取前文伏笔

    async def continue_text(self, request: ContinueRequest, on_text: Optional[OnText] = None,
                            on_reject: Optional[OnReject] = None) -> RefineResult:
        """生成续写草稿（不保存）。Writer 调用失败时抛出 LLMError。"""
        context = self.pipeline.context
        query = tail(request.preceding, 500) or request.outline
        references = await context.gather(request.project_id, query, request.chapter_index, "reader")
        hooks = await self.open_hooks(request.project_id, request.chapter_index)
        style = await self.pipeline.style_for(request.project_id)

        def prompt(feedback: str) -> str:
            return join_sections(
                section("参考资料", references),
                section("前文埋下的伏笔（可酌情呼应，已经回收的忽略）", hooks),
                section("文风要求", style.description if style else ""),
                section("文风示例（学习语感，不要照抄内容）", style_samples(style)),
                section("续写大纲 / 走向", request.outline),
                section("审校意见（必须执行）", feedback),
                section("新章节标题", request.title),
                section("前文（续写从这里接着往下写）", tail(request.preceding, PRECEDING_CHARS)),
                section("后文（续写结束时要能自然衔接到这里）", head(request.following, FOLLOWING_CHARS)),
                f"请接着前文续写{LENGTHS.get(request.target_chars, f'约 {request.target_chars} 字')}。"
                "只输出续写的正文，不要重复前文，不要写章节标题。",
            )

        async def review(candidate: str):
            author = await context.gather(request.project_id, query, request.chapter_index, "author")
            return await self.pipeline.ask_reviewer(join_sections(
                section("设定资料（作者视角）", author),
                section("文风档案", style_text(style)),
                section("续写大纲", request.outline),
                section("前文", tail(request.preceding, PRECEDING_CHARS)),
                section("后文", head(request.following, FOLLOWING_CHARS)),
                section("续写", excerpt(candidate)),
                CONTINUE_REVIEW_INSTRUCTION,
                STYLE_REVIEW_INSTRUCTION if style else "",
            ), with_style=bool(style))

        return await write_with_review(
            self.pipeline.settings,
            lambda feedback: self.pipeline.stream_writer(prompt(feedback), request.persona, on_text),
            review,
            on_reject,
        )

    async def open_hooks(self, project_id: Optional[str], chapter_index: int) -> str:
        """当前章节之前各章埋下的伏笔，越近越优先（无法判断是否已回收，交给模型斟酌）。"""
        if not project_id or not self.chapter_store:
            return ""
        chapters = (await self.projects.get_chapters(project_id))[:max(chapter_index - 1, 0)]
        memories = await self.chapter_store.for_project(project_id)
        lines: list[str] = []
        for chapter in reversed(chapters):
            memory = memories.get(chapter["id"])
            lines[:0] = [f"- {chapter['title']}：{h}" for h in (memory.hooks if memory else [])]
            if len(lines) >= MAX_HOOKS:
                break
        return "\n".join(lines[-MAX_HOOKS:])

    async def adopt_chapter(self, project_id: str, title: str, text: str) -> str:
        """采纳续写的新章节：写入全书末尾并进入向量记忆，返回新章节 id。"""
        chapter_id = await self.projects.add_chapter(project_id, title.strip() or "新章节", text.strip())
        if self.rag:
            await self.rag.aindex_chapter(project_id, chapter_id, text)
        return chapter_id
