"""上传兼容性：旧版同步文件流和新版异步文件都要完整读取。"""
import asyncio
from io import BytesIO
from tempfile import SpooledTemporaryFile
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.ui.session import Session


@pytest.mark.parametrize("large", [False, True])
def test_legacy_upload_keeps_all_bytes(large):
    raw = "第一章 开端\n这是小说正文。\n".encode("utf-8") * (100_000 if large else 1)
    with SpooledTemporaryFile(max_size=1024 * 1024) if large else BytesIO() as stream:
        stream.write(raw)
        stream.seek(0)
        event = SimpleNamespace(name="小说.txt", content=stream)
        result = asyncio.run(Session(SimpleNamespace())._extract_upload_info(event))
    assert result == ("小说.txt", raw)


def test_async_upload_keeps_all_bytes():
    raw = "第一章 开端\n这是小说正文。".encode("utf-8")
    file = SimpleNamespace(name="小说.txt", read=AsyncMock(return_value=raw))
    event = SimpleNamespace(file=file)
    result = asyncio.run(Session(SimpleNamespace())._extract_upload_info(event))
    assert result == ("小说.txt", raw)
    file.read.assert_awaited_once()


def test_failed_read_is_not_retried():
    read = Mock(side_effect=OSError("读取失败"))
    event = SimpleNamespace(name="小说.txt", content=SimpleNamespace(read=read))
    with pytest.raises(OSError, match="读取失败"):
        asyncio.run(Session(SimpleNamespace())._extract_upload_info(event))
    read.assert_called_once_with()
