"""小说助手问答：结合本章内容、相关记忆和人物关系回答问题。

- 本章模式：读者视角，只用截至当前章节已揭示的关系，不剧透后文
- 全书模式：作者视角，可以使用全部设定（提问的是作者本人）
"""
from typing import AsyncIterator

from src.llm.prompts import assemble_system_prompt, join_sections, section
from src.services.context import ContextBuilder

CHAPTER_EXCERPT_CHARS = 2000


class ChatService:
    def __init__(self, llm, settings, context: ContextBuilder):
        self.llm = llm
        self.settings = settings
        self.context = context

    async def answer(
        self,
        question: str,
        project_id: str | None,
        chapter_index: int,
        chapter_text: str = "",
        mode: str = "chapter",
    ) -> AsyncIterator[str]:
        """流式回答。模型调用失败时抛出 LLMError。"""
        if mode == "chapter":
            references = await self.context.gather(project_id, question, chapter_index, "reader")
            excerpt = chapter_text[:CHAPTER_EXCERPT_CHARS]
        else:
            references = await self.context.gather(project_id, question, chapter_index, "author")
            excerpt = ""
        prompt = join_sections(section("本章内容", excerpt), section("参考资料", references), section("问题", question))
        system = assemble_system_prompt(self.settings.get_role_config("chat"), self.settings.is_nsfw_enabled())
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        async for token in self.llm.stream(self.settings.resolve_role("chat"), messages):
            yield token
