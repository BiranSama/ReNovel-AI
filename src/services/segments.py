"""编辑器里的段落：原文、候选与采纳状态（纯函数，不依赖界面）。

每段是一个 dict：
    original   载入时的正文
    revised    候选：AI 改写结果或手动修改（右侧输入框）
    adopted    是否采纳候选；未采纳时保存原文
    history    之前采纳过的候选，撤销时依次恢复

AI 改写完成后自动采纳（保存即生效）；撤销先退回上一个候选，再退回原文；退回原文后候选仍保留，可以重新采纳。
"""


def new_segment(original: str = "", revised: str = "") -> dict:
    return {"original": original, "revised": revised, "adopted": bool(revised.strip()), "history": []}


def split_text(text: str) -> list[dict]:
    if not text:
        return []
    return [new_segment(line.strip()) for line in text.split("\n") if line.strip()]


def ensure_fields(seg: dict) -> dict:
    """补齐旧格式段落缺少的字段。"""
    seg.setdefault("original", "")
    seg.setdefault("revised", "")
    seg.setdefault("adopted", bool((seg["revised"] or "").strip()))
    seg.setdefault("history", [])
    return seg


def current(seg: dict) -> str:
    """这一段现在生效的文字：采纳了候选用候选，否则用原文。"""
    ensure_fields(seg)
    revised = seg["revised"] or ""
    return revised if seg["adopted"] and revised.strip() else seg["original"] or ""


def merge(segments: list[dict]) -> str:
    return "\n\n".join(text for text in (current(s) for s in segments) if text.strip())


def propose(seg: dict, text: str) -> None:
    """AI 改写完成：作为新的候选并采纳；之前采纳的候选留作撤销用。"""
    ensure_fields(seg)
    previous = seg["revised"] or ""
    if seg["adopted"] and previous.strip() and previous != text:
        seg["history"].append(previous)
    seg["revised"], seg["adopted"] = text, bool(text.strip())


def edit(seg: dict, text: str) -> None:
    """在右侧输入框里手动修改候选：视为采纳。"""
    ensure_fields(seg)
    seg["revised"], seg["adopted"] = text, bool(text.strip())


def can_undo(seg: dict) -> bool:
    ensure_fields(seg)
    return bool(seg["history"]) or (seg["adopted"] and bool((seg["revised"] or "").strip()))


def undo(seg: dict) -> bool:
    """撤销一步：退回上一个采纳的候选；没有更早的候选时退回原文（候选保留，可重新采纳）。"""
    ensure_fields(seg)
    if seg["history"]:
        seg["revised"], seg["adopted"] = seg["history"].pop(), True
        return True
    if seg["adopted"]:
        seg["adopted"] = False
        return True
    return False


def can_adopt(seg: dict) -> bool:
    ensure_fields(seg)
    return not seg["adopted"] and bool((seg["revised"] or "").strip())


def adopt(seg: dict) -> None:
    ensure_fields(seg)
    if (seg["revised"] or "").strip():
        seg["adopted"] = True
