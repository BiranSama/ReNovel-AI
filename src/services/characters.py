"""角色档案：从各章的章节记忆自动汇总别名、性格、状态变化与出场章节，人物关系取自知识图谱；
用户的手动修订（别名、性格、备注、隐藏）优先于自动汇总，重新整理记忆也不会覆盖。

同一角色的不同称呼（章节记忆里的 aliases，或用户添加的别名）会合并成一个档案。
"""
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional

from src.core.chapter_memory_store import ChapterMemory, ChapterMemoryStore, CharacterOverride


@dataclass
class StatusChange:
    chapter_index: int  # 第几章（从 1 开始，与图谱的章节序号一致）
    chapter_title: str
    status: str


@dataclass
class CharacterProfile:
    name: str
    aliases: list[str] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)       # 各章体现的性格（自动汇总）
    statuses: list[StatusChange] = field(default_factory=list)
    chapters: list[int] = field(default_factory=list)     # 出场章节序号
    manual_traits: str = ""                               # 用户填写的性格，优先于自动汇总
    notes: str = ""                                       # 用户备注
    edited: bool = False
    hidden: bool = False                                  # 用户标记为误识别

    @property
    def names(self) -> list[str]:
        return [self.name, *self.aliases]

    def traits_text(self) -> str:
        return self.manual_traits or "；".join(self.traits)

    def statuses_before(self, chapter_index: Optional[int]) -> list[StatusChange]:
        """读者视角：只取当前章节之前的状态变化。chapter_index 为空时取全部（作者视角）。"""
        if chapter_index is None:
            return list(self.statuses)
        return [s for s in self.statuses if s.chapter_index < chapter_index]


class _Groups:
    """并查集：把同一角色的不同称呼归到一组。"""

    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, name: str) -> str:
        self.parent.setdefault(name, name)
        while self.parent[name] != name:
            self.parent[name] = self.parent[self.parent[name]]
            name = self.parent[name]
        return name

    def union(self, a: str, b: str) -> None:
        self.parent[self.find(a)] = self.find(b)

    def members(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for name in self.parent:
            groups.setdefault(self.find(name), []).append(name)
        return groups


def build_profiles(chapters: list[dict], memories: dict[str, ChapterMemory],
                   overrides: dict[str, CharacterOverride], include_hidden: bool = False) -> list[CharacterProfile]:
    """按出场次数从多到少排列；被用户隐藏的角色默认不列出（include_hidden 时列出并标记，可以取消隐藏）。"""
    groups, mentions, first_seen = _Groups(), Counter(), {}
    ordered = [(i, c, memories.get(c["id"])) for i, c in enumerate(chapters, start=1)]
    for _, _, memory in ordered:
        if not memory:
            continue
        for name in memory.characters:
            mentions[name] += 1
            first_seen.setdefault(name, len(first_seen))
            groups.find(name)
        for note in memory.notes:
            first_seen.setdefault(note.name, len(first_seen))
            groups.find(note.name)
            for alias in note.aliases:
                groups.union(alias, note.name)
    for name, override in overrides.items():
        first_seen.setdefault(name, len(first_seen))
        groups.find(name)
        for alias in override.aliases:
            groups.union(alias, name)

    profiles, canonical_of = {}, {}
    for members in groups.members().values():
        edited = sorted((m for m in members if m in overrides), key=lambda m: first_seen.get(m, 1 << 30))
        # 用户修订过的名字优先（几个都修订过时，取把别的称呼加为别名、促成合并的那一个）；
        # 否则取出场最多、最早出现的称呼
        merging = [m for m in edited if any(a in members and a != m for a in overrides[m].aliases)]
        name = (merging or edited)[0] if edited else \
            min(members, key=lambda m: (-mentions[m], first_seen.get(m, 1 << 30)))
        override = _merged_override(name, [overrides[m] for m in edited])
        aliases = [a for a in sorted(members, key=lambda m: first_seen.get(m, 1 << 30)) if a != name]
        aliases += [a for a in override.aliases if a not in aliases and a != name]
        profiles[name] = CharacterProfile(name, aliases, manual_traits=override.traits, notes=override.notes,
                                          edited=name in overrides, hidden=override.hidden)
        for member in members:
            canonical_of[member] = name

    for index, chapter, memory in ordered:
        if not memory:
            continue
        for member in memory.characters:
            profile = profiles[canonical_of[member]]
            if index not in profile.chapters:
                profile.chapters.append(index)
        for note in memory.notes:
            profile = profiles[canonical_of[note.name]]
            if note.traits and note.traits not in profile.traits:
                profile.traits.append(note.traits)
            if note.status:
                profile.statuses.append(StatusChange(index, chapter.get("title", ""), note.status))

    listed = [p for p in profiles.values() if include_hidden or not p.hidden]
    return sorted(listed, key=lambda p: (p.hidden, -len(p.chapters), first_seen.get(p.name, 1 << 30)))


def _merged_override(name: str, edited: list[CharacterOverride]) -> CharacterOverride:
    """合并成一个角色的几份修订：以 name 那份为准，其他几份的性格、备注接在后面，不丢手动填写的内容。"""
    main = next((o for o in edited if o.name == name), CharacterOverride(name))
    traits, notes = main.traits, main.notes
    for other in edited:
        if other is main:
            continue
        if other.traits and other.traits not in traits:
            traits = "；".join(t for t in (traits, other.traits) if t)
        if other.notes and other.notes not in notes:
            notes = "；".join(n for n in (notes, other.notes) if n)
    return CharacterOverride(name, main.aliases, traits, notes, main.hidden)


def mentioned(profiles: list[CharacterProfile], text: str) -> list[CharacterProfile]:
    """文本里提到（本名或别名）的角色。"""
    return [p for p in profiles if any(n and n in text for n in p.names)]


class CharacterService:
    def __init__(self, projects, store: ChapterMemoryStore,
                 graph_provider: Callable[[Optional[str]], object] = lambda project_id: None):
        self.projects = projects
        self.store = store
        self.graph_provider = graph_provider

    async def profiles(self, project_id: str, include_hidden: bool = False) -> list[CharacterProfile]:
        if not project_id:
            return []
        chapters = await self.projects.get_chapters(project_id)
        return build_profiles(chapters, await self.store.for_project(project_id),
                              await self.store.overrides(project_id), include_hidden)

    def relations(self, project_id: str, profile: CharacterProfile, chapter_index: int = 1 << 30,
                  view: str = "author") -> list[str]:
        """图谱里与这个角色（含别名）相关的关系。"""
        graph = self.graph_provider(project_id)
        if not graph:
            return []
        lines = []
        for name in profile.names:
            for line in graph.query_context(name, chapter_index, view).splitlines():
                if line not in lines:
                    lines.append(line)
        return lines

    async def save_override(self, project_id: str, override: CharacterOverride) -> None:
        await self.store.save_override(project_id, override)
