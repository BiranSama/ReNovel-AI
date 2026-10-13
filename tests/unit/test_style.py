"""文风：档案存取、从原文提炼、预设；改写与审校的提示词带上文风档案，修改档案后下一次改写立即生效。"""
import asyncio
import json

import pytest

from src.core.project_manager import ProjectManager
from src.core.settings import AppSettings
from src.core.style_store import StyleProfile, StyleStore
from src.services.context import ContextBuilder
from src.services.refine import RefinePipeline, RefineRequest
from src.services.style import MAX_PARAGRAPH_CHARS, PRESET_NAMES, StyleExtractError, StyleService, pick_candidates

PARAGRAPH = "他把烟按灭在窗台上，转身去倒水。水壶是空的。他站了一会儿，又把烟盒拿起来，看了看窗外的雨。"


class Config:
    def load_config(self):
        return {r: {"api_key": "k", "model": r} for r in ("writer", "reviewer", "analyzer")} | {"enable_reviewer": True}

    def save_config(self, config):
        pass


class FakeLLM:
    def __init__(self, reply='{"description": "冷静的白描。", "samples": [2, 0, 99, "x", 2]}', review=None):
        self.prompts, self.reply = {}, reply
        self.review = review or json.dumps({"score": 9, "suggestion": "好", "style_score": 7})

    async def complete(self, config, messages):
        self.prompts.setdefault(config["model"], []).append(messages[-1]["content"])
        return self.review if config["model"] == "reviewer" else self.reply

    async def stream(self, config, messages):
        self.prompts.setdefault(config["model"], []).append(messages[-1]["content"])
        yield "改写。"


@pytest.fixture
def env(tmp_path):
    pm = ProjectManager()
    pm.db_path = str(tmp_path / "t.db")
    store = StyleStore(pm.db_path)

    async def init():
        await pm.init_db()
        await store.init_db()
        pid = await pm.create_project("书")
        body = "\n".join(f"{i}号段落：{PARAGRAPH}" for i in range(30))
        await pm.import_content(pid, f"第一章 开端\n{body}\n第二章 结尾\n短句。\n")
        return pid

    return pm, store, asyncio.run(init())


def test_store_round_trip_and_clone(env):
    _, store, pid = env
    assert asyncio.run(store.get(pid)) is None and asyncio.run(store.get(None)) is None
    asyncio.run(store.save(pid, StyleProfile(" 描述 ", ["甲", " ", "乙"], "手动")))
    assert asyncio.run(store.get(pid)) == StyleProfile("描述", ["甲", "乙"], "手动")
    asyncio.run(store.clone(pid, "copy"))
    assert asyncio.run(store.get("copy")).description == "描述"


def test_candidates_are_spread_across_the_book():
    texts = ["\n".join(f"{i:02d}" + "字" * 50 for i in range(100)), "太短"]
    picked = pick_candidates(texts, limit=4)
    assert [p[:2] for p in picked] == ["00", "25", "50", "75"]


def test_extract_saves_description_and_valid_samples(env):
    pm, store, pid = env
    llm = FakeLLM()
    profile = asyncio.run(StyleService(llm, AppSettings(Config()), pm, store).extract(pid))
    assert profile.description == "冷静的白描。" and profile.source == "提炼自原文"
    assert len(profile.samples) == 1 and profile.samples[0].startswith("2")  # 越界、重复、非数字的编号被忽略
    assert "[1] 0号段落" in llm.prompts["analyzer"][0]
    assert asyncio.run(store.get(pid)) == profile


def test_extract_errors(env, tmp_path):
    pm, store, pid = env
    with pytest.raises(StyleExtractError, match="有效的风格描述"):
        asyncio.run(StyleService(FakeLLM(reply="抱歉"), AppSettings(Config()), pm, store).extract(pid))

    async def tiny_book():
        other = await pm.create_project("短篇")
        await pm.import_content(other, "第一章 只有一句\n很短。\n")
        return other

    with pytest.raises(StyleExtractError, match="正文太少"):
        asyncio.run(StyleService(FakeLLM(), AppSettings(Config()), pm, store).extract(asyncio.run(tiny_book())))


@pytest.mark.parametrize("description", [{"视角": "第三人称", "句式": "短句"}, ["短句"], 3])
def test_non_string_description_is_rejected(env, description):
    """模型把描述写成对象或列表时算提炼失败，不把 Python 的表示形式存进档案、带进每次改写。"""
    pm, store, pid = env
    reply = json.dumps({"description": description, "samples": [1]}, ensure_ascii=False)
    with pytest.raises(StyleExtractError, match="有效的风格描述"):
        asyncio.run(StyleService(FakeLLM(reply=reply), AppSettings(Config()), pm, store).extract(pid))
    assert asyncio.run(store.get(pid)) is None


def test_long_paragraphs_are_trimmed_instead_of_dropped(env):
    """有的 TXT 一章只有一行：过长的段落截到句末再用，不会因此报「正文太少」。"""
    pm, store, _ = env

    async def one_line_book():
        pid = await pm.create_project("一行一章")
        line = "".join(f"第{i}句写得很长很长，节奏很慢。" for i in range(80))
        await pm.import_content(pid, f"第一章 开端\n{line}\n第二章 结尾\n{line}\n")
        return pid

    pid = asyncio.run(one_line_book())
    candidates = pick_candidates([asyncio.run(pm.get_chapter_content(c["id"]))
                                  for c in asyncio.run(pm.get_chapters(pid))])
    assert len(candidates) == 2 and all(len(c) <= MAX_PARAGRAPH_CHARS and c.endswith("。") for c in candidates)
    profile = asyncio.run(StyleService(FakeLLM(reply='{"description": "慢。", "samples": [1]}'),
                                       AppSettings(Config()), pm, store).extract(pid))
    assert profile.description == "慢。"


def test_extraction_does_not_overwrite_a_profile_changed_meanwhile(env):
    """提炼要等模型：期间套用了预设或手动保存，以后来的操作为准，提炼结果不覆盖。"""
    pm, store, pid = env
    service = StyleService(None, AppSettings(Config()), pm, store)

    class SlowLLM(FakeLLM):
        async def complete(self, config, messages):
            await service.apply_preset(pid, "古风")  # 等模型时用户套用了预设
            return await super().complete(config, messages)

    service.llm = SlowLLM()
    with pytest.raises(StyleExtractError, match="被修改过"):
        asyncio.run(service.extract(pid))
    assert asyncio.run(store.get(pid)).source == "预设：古风"


def test_style_panel_ignores_a_refresh_for_a_project_no_longer_open():
    """很快地连续切换项目：前一个项目的档案读得慢、后到时，不能显示在当前项目的面板里。"""
    from types import SimpleNamespace

    from src.ui.components.style_panel import StylePanel

    state = SimpleNamespace(current_project_id="A")

    async def get(project_id):
        state.current_project_id = "B"  # 读取 A 的档案期间切到了 B
        return StyleProfile("A 的文风")

    panel = SimpleNamespace(session=SimpleNamespace(state=state, services=SimpleNamespace(style=SimpleNamespace(get=get))),
                            profile=None, rendered=[])
    panel._render = lambda: panel.rendered.append(panel.profile)
    asyncio.run(StylePanel.refresh(panel))
    assert panel.profile is None and panel.rendered == []


def test_presets_can_be_applied(env):
    pm, store, pid = env
    assert PRESET_NAMES == ["白描", "古风", "轻小说"]
    profile = asyncio.run(StyleService(FakeLLM(), AppSettings(Config()), pm, store).apply_preset(pid, "古风"))
    assert profile.source == "预设：古风" and "半文半白" in asyncio.run(store.get(pid)).description


def refine(env, llm):
    _, store, pid = env
    pipeline = RefinePipeline(llm, AppSettings(Config()), ContextBuilder(None), styles=store)
    return asyncio.run(pipeline.refine(RefineRequest(text="原文。", instruction="润色", project_id=pid)))


def test_prompts_include_style_profile_and_style_score(env):
    _, store, pid = env
    asyncio.run(store.save(pid, StyleProfile("短句白描。", ["示例一。", "示例二。"], "手动")))
    llm = FakeLLM()
    result = refine(env, llm)
    writer, reviewer = llm.prompts["writer"][0], llm.prompts["reviewer"][0]
    assert "【文风要求】\n短句白描。" in writer and "- 示例一。\n- 示例二。" in writer
    assert "【文风档案】\n短句白描。\n示例：" in reviewer and "style_score" in reviewer
    assert result.review.style_score == 7


def test_without_profile_there_is_no_style_section(env):
    llm = FakeLLM()
    result = refine(env, llm)
    assert "文风" not in llm.prompts["writer"][0] and "style_score" not in llm.prompts["reviewer"][0]
    assert result.review.style_score is None


def test_edited_profile_takes_effect_on_next_rewrite(env):
    """阶段 4 的完成标准：修改档案后下一次改写立即生效。"""
    _, store, pid = env
    asyncio.run(store.save(pid, StyleProfile("旧文风。", [], "手动")))
    llm = FakeLLM()
    refine(env, llm)
    asyncio.run(store.save(pid, StyleProfile("新文风：全部用短句。", [], "手动")))
    refine(env, llm)
    assert "旧文风" in llm.prompts["writer"][0]
    assert "【文风要求】\n新文风：全部用短句。" in llm.prompts["writer"][1] and "旧文风" not in llm.prompts["writer"][1]


def test_non_list_samples_fall_back_to_default_paragraphs(env):
    pm, store, pid = env
    llm = FakeLLM(reply='{"description": "冷静。", "samples": 1}')
    profile = asyncio.run(StyleService(llm, AppSettings(Config()), pm, store).extract(pid))
    assert profile.description == "冷静。" and len(profile.samples) == 2


def test_saving_keeps_at_most_three_samples(env):
    pm, store, pid = env
    service = StyleService(FakeLLM(), AppSettings(Config()), pm, store)
    asyncio.run(service.save(pid, StyleProfile("描述", ["一", "", "二", "三", "四"], "手动")))
    assert asyncio.run(store.get(pid)).samples == ["一", "二", "三"]


def test_each_retry_writes_and_reviews_with_the_same_fresh_profile(env):
    """重试期间档案被修改：下一稿按新档案写，也按新档案审。"""
    _, store, pid = env
    asyncio.run(store.save(pid, StyleProfile("旧文风。", [], "手动")))

    class EditingLLM(FakeLLM):
        async def complete(self, config, messages):
            prompt = messages[-1]["content"]
            self.prompts.setdefault(config["model"], []).append(prompt)
            if len(self.prompts["reviewer"]) == 1:  # 第一次审校时，档案在另一个标签页被改了
                await store.save(pid, StyleProfile("新文风。", [], "手动"))
                return json.dumps({"score": 3, "suggestion": "改"})
            return json.dumps({"score": 9, "suggestion": "好"})

    llm = EditingLLM()
    pipeline = RefinePipeline(llm, AppSettings(Config()), ContextBuilder(None), styles=store)
    pipeline.settings.config["review_mode"] = "auto"
    asyncio.run(pipeline.refine(RefineRequest(text="原文。", instruction="润色", project_id=pid)))
    assert "旧文风" in llm.prompts["writer"][0] and "旧文风" in llm.prompts["reviewer"][0]
    assert "新文风" in llm.prompts["writer"][1] and "新文风" in llm.prompts["reviewer"][1]
