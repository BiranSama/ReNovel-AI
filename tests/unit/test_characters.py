"""角色档案：按别名合并、汇总性格与状态变化、读者视角只看前文、手动修订优先、隐藏误识别的角色。"""
import asyncio

from src.core.chapter_memory_store import CharacterNote, ChapterMemory, ChapterMemoryStore, CharacterOverride
from src.core.project_manager import ProjectManager
from src.services.characters import CharacterService, build_profiles, mentioned

CHAPTERS = [{"id": f"c{i}", "title": f"第{i}章"} for i in range(1, 5)]


def memories():
    return {
        "c1": ChapterMemory("c1", "相遇", ["张三", "李四"], notes=[
            CharacterNote("张三", ["三哥"], "念旧", ""), CharacterNote("李四", [], "沉稳", "")]),
        "c2": ChapterMemory("c2", "冲突", ["三哥", "李四", "王五"], notes=[
            CharacterNote("三哥", [], "冲动", "左臂受伤")]),
        "c3": ChapterMemory("c3", "离别", ["张三"], notes=[CharacterNote("张三", [], "念旧", "离开长安")]),
    }


def by_name(profiles):
    return {p.name: p for p in profiles}


def test_aliases_merge_into_one_profile():
    profiles = by_name(build_profiles(CHAPTERS, memories(), {}))
    zhang = profiles["张三"]  # 出场最多的称呼作为名字
    assert zhang.aliases == ["三哥"] and "三哥" not in profiles
    assert zhang.chapters == [1, 2, 3]
    assert zhang.traits == ["念旧", "冲动"]  # 去重，按出现顺序
    assert [(s.chapter_index, s.status) for s in zhang.statuses] == [(2, "左臂受伤"), (3, "离开长安")]
    assert list(profiles) == ["张三", "李四", "王五"]  # 出场多的在前


def test_reader_view_only_sees_earlier_statuses():
    zhang = by_name(build_profiles(CHAPTERS, memories(), {}))["张三"]
    assert [s.status for s in zhang.statuses_before(3)] == ["左臂受伤"]
    assert len(zhang.statuses_before(None)) == 2


def test_overrides_win_and_can_merge_or_hide():
    overrides = {
        "李四": CharacterOverride("李四", ["王五"], traits="外冷内热", notes="其实是卧底"),  # 用户认定王五就是李四
        "第4章": CharacterOverride("第4章", hidden=True),
    }
    profiles = by_name(build_profiles(CHAPTERS, memories(), overrides))
    li = profiles["李四"]
    assert "王五" not in profiles and li.aliases == ["王五"]
    assert (li.traits_text(), li.notes, li.edited) == ("外冷内热", "其实是卧底", True)
    assert li.chapters == [1, 2]
    assert "第4章" not in profiles


def test_mentioned_matches_aliases():
    profiles = build_profiles(CHAPTERS, memories(), {})
    assert [p.name for p in mentioned(profiles, "三哥推门而入")] == ["张三"]


def test_service_reads_store_and_saves_overrides(tmp_path):
    pm = ProjectManager()
    pm.db_path = str(tmp_path / "t.db")
    store = ChapterMemoryStore(pm.db_path)

    class Graph:
        def query_context(self, name, chapter, view):
            return {"张三": "- 张三 朋友 李四", "三哥": "- 王五 仇人 三哥\n- 张三 朋友 李四"}.get(name, "")

    service = CharacterService(pm, store, lambda pid: Graph())

    async def run():
        await pm.init_db()
        await store.init_db()
        pid = await pm.create_project("书")
        await pm.import_content(pid, "第一章 相遇\n正文。\n第二章 冲突\n正文。\n")
        ids = [c["id"] for c in await pm.get_chapters(pid)]
        for cid, memory in zip(ids, memories().values()):
            memory.chapter_id = cid
            await store.save(pid, memory)
        await service.save_override(pid, CharacterOverride("李四", notes="卧底"))
        return await service.profiles(pid)

    profiles = by_name(asyncio.run(run()))
    assert profiles["李四"].notes == "卧底" and profiles["张三"].chapters == [1, 2]
    assert service.relations("p", profiles["张三"]) == ["- 张三 朋友 李四", "- 王五 仇人 三哥"]
