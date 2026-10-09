"""审校未通过时的弹窗：对照原文与改写，用户选择按修改意见重写，或接受当前结果。"""
import asyncio
from typing import Optional

from nicegui import ui

from src.services.refine import Review


class ReviewDialog:
    def __init__(self):
        self._answer: Optional[asyncio.Future] = None
        with ui.dialog() as self.dialog, ui.card().classes('w-full max-w-6xl h-[90vh] flex flex-col border-t-4 border-red-500'):
            with ui.row().classes('justify-between w-full'):
                ui.label('⚠️ 总监意见：质量未达标').classes('text-lg font-bold text-red-600')
                self.score = ui.label().classes('text-xl font-bold bg-red-100 px-2 rounded')
            with ui.row().classes('flex-grow w-full gap-4 py-2 overflow-hidden'):
                with ui.column().classes('w-1/2 h-full full-height-col'):
                    ui.label('📄 原文').classes('font-bold text-gray-500')
                    self.original = ui.textarea().props('readonly borderless filled').classes('full-height-textarea bg-gray-100 rounded')
                with ui.column().classes('w-1/2 h-full full-height-col'):
                    ui.label('📝 当前改写').classes('font-bold text-gray-500')
                    self.candidate = ui.textarea().props('readonly borderless filled').classes('full-height-textarea bg-yellow-50 rounded')
            ui.label('💡 修改建议:').classes('font-bold text-indigo-500')
            self.feedback = ui.textarea().classes('w-full bg-white border p-1 rounded').props('outlined dense rows=2')
            with ui.row().classes('w-full justify-end items-center'):
                self.limit = ui.label('已达到最多重试次数，可接受当前结果后手动修改').classes('text-sm text-gray-500')
                self.retry = ui.button('AI 重写', on_click=lambda: self._resolve(self.feedback.value or '')) \
                    .props('outline color=indigo')
                ui.button('强制通过', on_click=lambda: self._resolve(None)).props('unelevated color=grey')
        self.dialog.on('hide', lambda: self._resolve(None))  # 点遮罩或按 Esc 关闭视为接受

    async def ask(self, review: Review, original: str, candidate: str, can_retry: bool = True) -> Optional[str]:
        """返回修改意见表示按意见重写；返回 None 表示接受当前结果。"""
        self.score.text = f'{review.score:g}分' if review.score is not None else '未评分'
        self.original.value, self.candidate.value = original, candidate
        self.feedback.value = review.suggestion
        self.retry.set_visibility(can_retry)
        self.limit.set_visibility(not can_retry)
        self._answer = asyncio.get_running_loop().create_future()
        self.dialog.open()
        answer = await self._answer
        return (answer.strip() or review.suggestion) if answer is not None else None

    def _resolve(self, answer: Optional[str]):
        if self._answer and not self._answer.done():
            self._answer.set_result(answer)
        self.dialog.close()
