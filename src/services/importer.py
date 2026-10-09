"""导入 TXT：识别编码、清洗文本、切分章节（纯函数，不碰数据库）。"""
import codecs
import re
from dataclasses import dataclass

from charset_normalizer import from_bytes

# 中文小说 TXT 实际会遇到的编码；限定候选范围，短文本也不会被误判成日韩编码
CANDIDATE_ENCODINGS = ["utf_8", "gb18030", "big5", "utf_16"]


class UnsupportedEncoding(ValueError):
    """无法识别文件编码。消息面向用户。"""


def decode_text(raw: bytes) -> str:
    """把上传的字节解码为文本：先看 BOM，再试 UTF-8，最后在 GBK / Big5 等之间检测。"""
    if raw.startswith(codecs.BOM_UTF8):
        raw = raw[len(codecs.BOM_UTF8):]
    elif raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    best = from_bytes(raw, cp_isolation=CANDIDATE_ENCODINGS).best()
    if best is None:
        raise UnsupportedEncoding("无法识别文件编码，请将文件另存为 UTF-8 后重新导入")
    return str(best)


def clean_text(text: str) -> str:
    return text.replace("\xa0", " ").replace("　", " ").replace("\r\n", "\n").replace("\r", "\n")


@dataclass
class ChapterDraft:
    title: str
    order_index: int
    content: str


PREFACE_TITLE = "【序章】"
WHOLE_TEXT_TITLE = "全文"

# 分卷标题：本身通常没有正文，和章节标题一起作为分隔符
VOLUME_PATTERN = re.compile(r'(?m)^\s*(?:第[0-9零一二三四五六七八九十百千]+卷|Vol\.?\s*\d+).*?$')
# (章节标题模式, 至少匹配几次才采用)，按可信度排列。“第X章”这类明确的标题出现一次就可信，
# 其余宽松模式容易误中普通短句，至少要出现 3 次
HEADING_PATTERNS = [
    (re.compile(r'(?m)^\s*(?:第[0-9零一二三四五六七八九十百千]+章|Chapter\s*\d+).*?$'), 1),
    (re.compile(r'(?m)^\s*\d+\.\s+.{0,30}$'), 3),
    (re.compile(r'(?m)^\s*[【\[]\s*.*?\s*[】\]].*?$'), 3),
    (re.compile(r'(?m)^\s*(?!.*[。，？！……：]$).{2,20}\s*$'), 3),
]
MAX_HEADING_LENGTH = 40
SENTENCE_ENDINGS = ("。", "，", "、", "；", "…", "”", "」", "』", '"')


def _is_heading(match: re.Match) -> bool:
    """排除恰好以“第X章”开头的正文句子：标题短，且不以句号、逗号、引号等结尾。"""
    line = match.group().strip()
    return 0 < len(line) <= MAX_HEADING_LENGTH and not line.endswith(SENTENCE_ENDINGS)


def _matches(pattern: re.Pattern, text: str) -> list[re.Match]:
    return [m for m in pattern.finditer(text) if _is_heading(m)]


def _find_headings(text: str) -> list[re.Match]:
    """章节标题取最可信的一种格式，再并入分卷标题；没有章节标题时只按分卷切分。"""
    volumes = _matches(VOLUME_PATTERN, text)
    for pattern, minimum in HEADING_PATTERNS:
        chapters = [m for m in _matches(pattern, text) if not VOLUME_PATTERN.match(m.group())]
        if len(chapters) >= minimum:
            by_start = {m.start(): m for m in volumes}
            for m in chapters:  # 同一行既是卷标题又匹配宽松模式时只算一次
                by_start.setdefault(m.start(), m)
            return [by_start[k] for k in sorted(by_start)]
    return volumes


def split_chapters(raw_text: str) -> list[ChapterDraft]:
    """切分章节。标题前的内容作为序章；只有标题、没有正文的（如分卷标题）跳过。"""
    text = clean_text(raw_text)
    headings = _find_headings(text)
    if not headings:
        return [ChapterDraft(WHOLE_TEXT_TITLE, 0, text)]

    chapters = []
    preface = text[:headings[0].start()].strip()
    if preface:
        chapters.append(ChapterDraft(PREFACE_TITLE, -1, preface))

    for i, heading in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        content = text[heading.end():end].strip()
        if content:
            chapters.append(ChapterDraft(heading.group().strip(), len(chapters) - bool(preface), content))
    return chapters
