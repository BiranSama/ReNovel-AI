"""酒馆角色卡解析的特征测试（TavernParser）。"""
import base64
import json

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from src.core.tavern_parser import TavernParser

CARD = {"name": "赛博侦探", "description": "疲惫的私家侦探", "personality": "冷漠", "scenario": "雨夜"}
CARD_V2 = {"spec": "chara_card_v2", "spec_version": "2.0", "data": CARD}


def write_json(path, card):
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return str(path)


def write_png(path, card=None, key="chara"):
    info = PngInfo()
    if card is not None:
        info.add_text(key, base64.b64encode(json.dumps(card, ensure_ascii=False).encode()).decode())
    Image.new("RGB", (4, 4)).save(path, pnginfo=info)
    return str(path)


@pytest.fixture
def parser():
    return TavernParser()


def test_json_v1(parser, tmp_path):
    assert parser.parse_card(write_json(tmp_path / "c.json", CARD)) == CARD


def test_json_v2_is_unwrapped(parser, tmp_path):
    assert parser.parse_card(write_json(tmp_path / "c.json", CARD_V2)) == CARD


@pytest.mark.parametrize("key", ["chara", "ccv3"])
def test_png_v1(parser, tmp_path, key):
    assert parser.parse_card(write_png(tmp_path / "c.png", CARD, key)) == CARD


@pytest.mark.xfail(strict=True, reason="已知 bug：PNG 里的 V2 卡没有像 JSON 那样解开 data 字段")
def test_png_v2_is_unwrapped(parser, tmp_path):
    assert parser.parse_card(write_png(tmp_path / "c.png", CARD_V2)) == CARD


@pytest.mark.parametrize("filename", ["plain.png", "card.txt"])
def test_invalid_files_return_empty_card(parser, tmp_path, filename):
    path = tmp_path / filename
    if filename.endswith(".png"):
        write_png(path)
    else:
        path.write_text("x")
    assert parser.parse_card(str(path))["name"] == "未知角色"


def test_missing_file_raises(parser, tmp_path):
    with pytest.raises(FileNotFoundError):
        parser.parse_card(str(tmp_path / "missing.json"))


def test_system_prompt_contains_card_fields(parser):
    prompt = parser.generate_system_prompt(CARD)
    for value in CARD.values():
        assert value in prompt
