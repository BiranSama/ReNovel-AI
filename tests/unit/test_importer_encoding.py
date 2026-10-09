"""导入编码识别：中文 TXT 常见编码都能正确解码，无法识别时报错而不是静默丢字。"""
import codecs

import pytest

from src.services.importer import UnsupportedEncoding, decode_text

SIMPLIFIED = "第一章 开端\n　　张三推开门，屋里一片漆黑，只有窗外透进来的月光。“你来了。”李四说。\n"
TRADITIONAL = "第一章 開端\n　　張三推開門，屋裡一片漆黑，只有窗外透進來的月光。「你來了。」李四說。\n"


@pytest.mark.parametrize("text, encoding", [
    (SIMPLIFIED, "utf-8"),
    (SIMPLIFIED * 20, "gbk"),
    (SIMPLIFIED, "gbk"),
    (SIMPLIFIED, "gb18030"),
    (TRADITIONAL * 20, "big5"),
    (TRADITIONAL, "big5"),
    (SIMPLIFIED, "utf-16"),
    ("第一章 开端", "gbk"),  # 很短的文本也不能被误判成日韩编码
])
def test_common_encodings_round_trip(text, encoding):
    assert decode_text(text.encode(encoding)) == text


def test_utf8_bom_is_stripped():
    assert decode_text(codecs.BOM_UTF8 + SIMPLIFIED.encode("utf-8")) == SIMPLIFIED


@pytest.mark.parametrize("raw", [bytes(range(256)) * 4, "Ce café est très bon. ".encode("latin-1") * 5])
def test_undecodable_input_is_rejected(raw):
    with pytest.raises(UnsupportedEncoding, match="无法识别文件编码"):
        decode_text(raw)
