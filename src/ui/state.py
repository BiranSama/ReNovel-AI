class AppState:
    """一个浏览器标签页的界面状态。每个页面创建一份，标签页之间互不影响。"""

    def __init__(self):
        # --- 数据 ---
        self.current_chapter_id = None
        self.current_project_id = None
        self.current_project_title = '未加载小说'
        self.active_system_prompt = None
        self.active_card_name = '默认 (无人设)'

        self.segments = []
        self.full_text_draft = ""
        self.full_text_history = []  # 全文工作台里被 AI 重写替换掉的草稿，撤销时恢复
        self.instruction = ""  # 底部的全局精修指令

        # --- 状态 ---
        self.view_mode = 'segment'
        self.is_batch_running = False
        self.stop_signal = False
        self.graph_task_running = False
        self.memory_task_running = False
        self.memory_pending = {}  # 项目 id → 等待整理的章节 id（None 表示全部）

        # --- UI 引用 ---
        self.ui = {
            'status_label': None,
            'status_progress': None,
            'project_title': None,
            'project_list': None,
            'chapter_list': None,
            'backup_list': None,
            'backup_dialog': None,
        }
