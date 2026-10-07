"""章节记忆：只从已保存正文整理、内容不变不重复整理、短章节不调用模型、返回无效时下次重试、
已知角色传给后面的章节、副本复制记忆。用假的 LLM，不联网。"""
import asyncio
import json

import pytest

from src.core.chapter_memory_store import ChapterMemory, ChapterMemoryStore
from src.core.project_manager import ProjectManager
from src.core.settings import AppSettings
from src.llm import LLMError
from src.services.batch import BatchService
from src.services.chapter_memory import ChapterMemoryService, MemoryParseError, parse_memory

BODY = "张三与李四在长安城外相遇，两人一见如故，约定次日同去拜访王五。" * 3


class StubConfig:
    def load_config(self):
        return {"writer": {"api_key": "k", "model": "writer"}}

    def save_config(self, config):
        pass


class FakeLLM:
    def __init__(self, replies=None, fail_after=None):
        self.prompts, self.replies, self.fail_after = [], list(replies or []), fail_after
        self.configs = []

    async def complete(self, config, messages):
        if self.fail_after is not None and len(self.prompts) >= self.fail_after:
            raise LLMError("额度不足")
        self.prompts.append(messages[-1]["content"])
        self.configs.append(config)
        if self.replies:
            return self.replies.pop(0)
        title = messages[-1]["content"].split("【章节标题】\n", 1)[1].split("\n", 1)[0]
        return json.dumps({"summary": f"{title}的摘要", "characters": ["张三", "李四"],
                           "events": ["张三遇见李四"]}, ensure_ascii=False)


@pytest.fixture
def env(tmp_path):
    pm = ProjectManager()
    pm.db_path = str(tmp_path / "t.db")
    store = ChapterMemoryStore(pm.db_path)

    async def init():
        await pm.init_db()
        await store.init_db()
        pid = await pm.create_project("书")
        await pm.import_content(pid, f"楔子\n第一章 相遇\n{BODY}\n第二章 拜访\n{BODY}\n第三章 短\n太短了。\n")
        return pid

    return pm, store, asyncio.run(init())


def service(env, llm):
    pm, store, _ = env
    return ChapterMemoryService(llm, AppSettings(StubConfig()), pm, store)


def memories(env):
    pm, store, pid = env
    by_id = asyncio.run(store.for_project(pid))
    return [(c["title"], by_id.get(c["id"])) for c in asyncio.run(pm.get_chapters(pid))]


def test_parse_memory():
    memory = parse_memory("c1", '好的：{"summary": " 摘要 ", "characters": ["张三", " ", 3], "events": "不是列表"}')
    assert (memory.summary, memory.characters, memory.events) == ("摘要", ["张三", "3"], [])
    with pytest.raises(MemoryParseError):
        parse_memory("c1", "我无法完成")


def test_update_summarizes_each_saved_chapter_once(env):
    llm = FakeLLM()
    assert asyncio.run(service(env, llm).update(env[2])) == 4  # 序章、两章正文、短章
    assert len(llm.prompts) == 2  # 太短的序章和第三章不调用模型
    result = dict(memories(env))
    assert result["第一章 相遇"].summary == "第一章 相遇的摘要"
    assert result["第一章 相遇"].characters == ["张三", "李四"]
    assert result["第三章 短"].is_empty and result["第三章 短"].fingerprint
    assert llm.configs[0]["model"] == "writer"  # 没单独设置时沿用 Writer 的连接

    assert asyncio.run(service(env, llm).update(env[2])) == 0  # 内容没变：不再调用模型
    assert len(llm.prompts) == 2


def test_known_characters_are_passed_to_later_chapters(env):
    llm = FakeLLM()
    asyncio.run(service(env, llm).update(env[2]))
    assert "【已知角色】" not in llm.prompts[0]
    assert "【已知角色】\n张三、李四" in llm.prompts[1]


def test_changed_chapter_is_summarized_again(env):
    pm, _, pid = env
    llm = FakeLLM()
    asyncio.run(service(env, llm).update(pid))
    second = asyncio.run(pm.get_chapters(pid))[2]["id"]
    asyncio.run(pm.update_chapter_content(second, BODY + "王五出场。"))
    assert asyncio.run(service(env, llm).update(pid)) == 1
    assert len(llm.prompts) == 3 and "王五出场" in llm.prompts[-1]


def test_cleared_chapter_gets_empty_memory(env):
    pm, _, pid = env
    asyncio.run(service(env, FakeLLM()).update(pid))
    first = asyncio.run(pm.get_chapters(pid))[1]["id"]
    asyncio.run(pm.update_chapter_content(first, ""))
    llm = FakeLLM()
    asyncio.run(service(env, llm).update(pid))
    assert llm.prompts == [] and dict(memories(env))["第一章 相遇"].is_empty


def test_invalid_reply_is_retried_next_time(env):
    pid = env[2]
    asyncio.run(service(env, FakeLLM(replies=["抱歉"])).update(pid))
    result = dict(memories(env))
    assert result["第一章 相遇"] is None and result["第二章 拜访"].summary  # 只有返回无效的那章没记录

    llm = FakeLLM()
    assert asyncio.run(service(env, llm).update(pid)) == 1 and len(llm.prompts) == 1


def test_llm_error_keeps_finished_chapters(env):
    with pytest.raises(LLMError):
        asyncio.run(service(env, FakeLLM(fail_after=1)).update(env[2]))
    result = dict(memories(env))
    assert result["第一章 相遇"].summary and result["第二章 拜访"] is None


def test_chapter_filter_limits_work(env):
    pm, _, pid = env
    first = asyncio.run(pm.get_chapters(pid))[1]["id"]
    llm = FakeLLM()
    asyncio.run(service(env, llm).update(pid, chapter_ids={first}))
    assert len(llm.prompts) == 1


def test_long_chapter_is_excerpted(env):
    pm, _, pid = env
    first = asyncio.run(pm.get_chapters(pid))[1]["id"]
    asyncio.run(pm.update_chapter_content(first, "甲" * 10000 + "中段" + "乙" * 10000))
    llm = FakeLLM()
    asyncio.run(service(env, llm).update(pid, chapter_ids={first}))
    assert "中段" not in llm.prompts[0] and "中间省略" in llm.prompts[0]


def test_backup_copies_memories_with_new_chapter_ids(env):
    pm, store, pid = env
    asyncio.run(service(env, FakeLLM()).update(pid))

    class NoRefine:
        pass

    backup, mapping = asyncio.run(BatchService(pm, NoRefine(), chapter_store=store).make_backup(pid))
    copied = asyncio.run(store.for_project(backup))
    first = asyncio.run(pm.get_chapters(pid))[1]["id"]
    assert copied[mapping[first]].summary == "第一章 相遇的摘要"
    assert len(copied) == 4 and asyncio.run(store.has_any(backup))

    llm = FakeLLM()
    asyncio.run(ChapterMemoryService(llm, AppSettings(StubConfig()), pm, store).update(backup))
    assert llm.prompts == []  # 副本内容没变，不需要重新整理


def test_store_round_trip(env):
    _, store, _ = env
    asyncio.run(store.save("p9", ChapterMemory("c9", "摘要", ["甲"], ["事件"], "f")))
    assert asyncio.run(store.for_project("p9")) == {"c9": ChapterMemory("c9", "摘要", ["甲"], ["事件"], "f")}
    assert not asyncio.run(store.has_any("nobody"))


def test_concurrent_updates_do_not_summarize_twice(env):
    llm = FakeLLM()
    memory_service = service(env, llm)

    async def both():
        await asyncio.gather(memory_service.update(env[2]), memory_service.update(env[2]))

    asyncio.run(both())
    assert len(llm.prompts) == 2  # 两章正文各一次
