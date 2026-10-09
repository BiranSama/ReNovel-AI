"""提示词组装与输出解析。"""
import pytest

from src.llm.prompts import assemble_system_prompt, join_sections, parse_json_object, section

BLOCKS = {"persona": "作家", "objective": "精修", "style": "白描", "safety": "合规", "nsfw_override": "成人"}


def test_blocks_are_assembled_in_order():
    assert assemble_system_prompt({"prompt_blocks": BLOCKS}) == (
        "### Role\n作家\n### Task\n精修\n### Style\n白描\n### Safety\n合规")


def test_nsfw_swaps_safety_block():
    assert assemble_system_prompt({"prompt_blocks": BLOCKS}, nsfw=True).endswith("### Safety\n成人")


def test_persona_goes_first_and_plain_system_prompt_is_supported():
    assert assemble_system_prompt({"system_prompt": "S"}, persona="人设") == "人设\nS"


@pytest.mark.parametrize("text, expected", [
    ('{"score": 9}', {"score": 9}),
    ('好的：\n```json\n{"score": 7, "suggestion": "删"}\n```', {"score": 7, "suggestion": "删"}),
    ("没有 JSON", None),
    ("{坏掉的}", None),
    ("[1, 2]", None),
])
def test_parse_json_object(text, expected):
    assert parse_json_object(text) == expected


def test_sections_skip_empty_bodies():
    assert join_sections(section("A", "x"), section("B", "  "), "尾") == "【A】\nx\n\n尾"
