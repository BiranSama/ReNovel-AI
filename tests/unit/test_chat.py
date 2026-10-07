"""问答：本章模式用读者视角并附本章内容，全书模式用作者视角。"""
import asyncio

from src.services.chat import ChatService


class FakeSettings:
    def get_role_config(self, role):
        return {"prompt_blocks": {"persona": "助手"}}

    def resolve_role(self, role):
        return {"model": role}

    def is_nsfw_enabled(self):
        return False


class FakeContext:
    def __init__(self):
        self.calls = []

    def gather(self, project_id, text, chapter_index, view):
        self.calls.append((project_id, text, chapter_index, view))
        return f"{view} 资料"


class FakeLLM:
    def __init__(self):
        self.messages = None

    async def stream(self, config, messages):
        self.messages = messages
        yield "答"


def ask(mode):
    llm, context = FakeLLM(), FakeContext()
    chat = ChatService(llm, FakeSettings(), context)

    async def run():
        return "".join([t async for t in chat.answer("主角是谁", "p1", 3, "本章正文" * 1000, mode)])

    return asyncio.run(run()), llm.messages, context.calls


def test_chapter_mode_uses_reader_view_and_chapter_excerpt():
    answer, messages, calls = ask("chapter")
    assert answer == "答"
    assert calls == [("p1", "主角是谁", 3, "reader")]  # 当前章节的读者视角，不剧透后文
    user = messages[-1]["content"]
    assert user.startswith("【本章内容】\n本章正文") and len(user) < 2200
    assert "【参考资料】\nreader 资料" in user and user.endswith("【问题】\n主角是谁")
    assert messages[0]["content"].startswith("### Role\n助手")


def test_book_mode_uses_author_view_without_excerpt():
    _, messages, calls = ask("book")
    assert calls[0][3] == "author"
    assert "本章内容" not in messages[-1]["content"]
