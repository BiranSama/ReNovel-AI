"""文风：从原文提炼文风档案（风格描述 + 代表段落），或套用预设；改写和审校时按档案执行。

- 提炼只读已保存的正文：在全书均匀抽取一批段落交给模型，模型写出风格描述并挑出最有代表性的几段
- 档案每次改写时重新读取，编辑后下一次改写立即生效
"""
from dataclasses import dataclass

from src.core.style_store import StyleProfile, StyleStore
from src.llm.prompts import assemble_system_prompt, join_sections, parse_json_object, section

CANDIDATE_PARAGRAPHS = 12   # 交给模型挑选的候选段落数
MIN_PARAGRAPH_CHARS = 20    # 太短的段落（如单句对白）不足以体现文风
MAX_PARAGRAPH_CHARS = 400
MAX_SAMPLES = 3
EXTRACT_INSTRUCTION = (
    "请提炼这本书的文风：从叙述视角、句式长短、用词、修辞、对白与描写的比例、节奏几个方面写出 200 字以内的风格描述，"
    "并从上面的段落里挑出最能代表这种文风的 2 到 3 段。只输出 JSON："
    '{"description": "风格描述", "samples": [段落编号]}'
)


class StyleExtractError(ValueError):
    """无法提炼文风（正文太少或模型返回无效）。消息面向用户。"""


@dataclass(frozen=True)
class StylePreset:
    name: str
    description: str
    samples: tuple[str, ...]


PRESETS = [
    StylePreset(
        "白描",
        "零度叙述，克制冷静。多用短句和动作、对白推进情节，不直接写人物心理和情绪，"
        "少用形容词与比喻，情绪通过细节和动作侧面流露。",
        ("他把烟按灭在窗台上，转身去倒水。水壶是空的。他站了一会儿，又把烟盒拿起来。",
         "“你走吧。”她说。门开了又关上，楼道里的灯亮了一下，灭了。"),
    ),
    StylePreset(
        "古风",
        "半文半白，用词典雅，多用四字短语与对仗，讲究意境与留白；称谓、器物、礼节符合古代语境，"
        "避免现代口语和网络用语。",
        ("暮色四合，长街上灯火次第亮起。她立在檐下，听雨打芭蕉，久久不语。",
         "“公子此去，山高水长，望自珍重。”他拱手一揖，翻身上马，再未回头。"),
    ),
    StylePreset(
        "轻小说",
        "第一人称或贴近主角的视角，口语化、节奏轻快，大量对白和内心吐槽，善用夸张与反差制造笑点，"
        "段落短，场景切换快。",
        ("等一下，这个展开不对吧？我只是想买个面包而已，为什么会被卷进魔王军的面试啊！",
         "“所以说，你就是新来的勇者？”少女上下打量了我一眼，叹了口气，“看起来好弱。”"),
    ),
]
PRESET_NAMES = [p.name for p in PRESETS]


def preset_profile(name: str) -> StyleProfile:
    preset = next(p for p in PRESETS if p.name == name)
    return StyleProfile(preset.description, list(preset.samples), f"预设：{preset.name}")


def pick_candidates(texts: list[str], limit: int = CANDIDATE_PARAGRAPHS) -> list[str]:
    """从各章正文里均匀抽取长度合适的段落。"""
    paragraphs = [p.strip() for text in texts for p in (text or "").split("\n")
                  if MIN_PARAGRAPH_CHARS <= len(p.strip()) <= MAX_PARAGRAPH_CHARS]
    if len(paragraphs) <= limit:
        return paragraphs
    step = len(paragraphs) / limit
    return [paragraphs[int(i * step)] for i in range(limit)]


class StyleService:
    def __init__(self, llm, settings, projects, store: StyleStore):
        self.llm = llm
        self.settings = settings
        self.projects = projects  # ProjectManager
        self.store = store

    async def get(self, project_id) -> StyleProfile:
        return await self.store.get(project_id) or StyleProfile()

    async def save(self, project_id: str, profile: StyleProfile) -> None:
        """保存档案；代表段落最多 MAX_SAMPLES 段（改写和审校也只用这么多）。"""
        samples = [s for s in profile.samples if s.strip()][:MAX_SAMPLES]
        await self.store.save(project_id, StyleProfile(profile.description, samples, profile.source))

    async def apply_preset(self, project_id: str, name: str) -> StyleProfile:
        profile = preset_profile(name)
        await self.store.save(project_id, profile)
        return profile

    async def extract(self, project_id: str) -> StyleProfile:
        """从已保存的正文提炼文风档案并保存。模型调用失败抛 LLMError，提炼不出来抛 StyleExtractError。"""
        chapters = await self.projects.get_chapters(project_id)
        texts = [await self.projects.get_chapter_content(c["id"]) or "" for c in chapters]
        candidates = pick_candidates(texts)
        if len(candidates) < 2:
            raise StyleExtractError("正文太少，无法提炼文风；可以先套用预设，或手动填写")
        numbered = "\n".join(f"[{i + 1}] {p}" for i, p in enumerate(candidates))
        prompt = join_sections(section("段落", numbered), EXTRACT_INSTRUCTION)
        system = assemble_system_prompt(self.settings.get_role_config("analyzer"), self.settings.is_nsfw_enabled())
        raw = await self.llm.complete(self.settings.resolve_role("analyzer"),
                                      [{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        data = parse_json_object(raw) or {}
        description = data.get("description")
        description = description.strip() if isinstance(description, str) else ""  # 对象、列表等不能直接当描述用
        if not description:
            raise StyleExtractError("模型没有返回有效的风格描述，请重试")
        samples = []
        indices = data.get("samples") if isinstance(data.get("samples"), list) else []  # 格式不对时用默认段落
        for index in indices:
            try:
                number = int(index)
            except (TypeError, ValueError):
                continue
            if 1 <= number <= len(candidates) and candidates[number - 1] not in samples:
                samples.append(candidates[number - 1])
        profile = StyleProfile(description, samples[:MAX_SAMPLES] or candidates[:2], "提炼自原文")
        await self.store.save(project_id, profile)
        return profile
