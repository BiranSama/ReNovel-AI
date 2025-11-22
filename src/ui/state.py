from nicegui import ui

class AppState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppState, cls).__new__(cls)
            cls._instance.reset()
        return cls._instance

    def reset(self):
        # --- 数据 ---
        self.current_chapter_id = None
        self.current_project_id = None
        self.current_project_title = '未加载小说'
        self.active_system_prompt = None
        self.active_card_name = '默认 (无人设)'
        
        self.segments = []        
        self.full_text_draft = "" 
        
        # --- 状态 ---
        self.view_mode = 'segment'
        self.is_batch_running = False
        self.stop_signal = False
        self.graph_task_running = False
        
        self.settings = None 
        
        # --- UI 引用 ---
        self.ui = {
            'status_label': None,
            'status_progress': None,
            'persona_label': None,
            'project_title': None,
            'chapter_list': None,
            'backup_list': None,     
            'backup_dialog': None,   # 备份弹窗引用
            'graph_chart': None,
            'chat_mode': None,
            'chat_container': None,
            'chat_input': None,      # [修复] 新增 Chat Input 引用
            'full_text_area': None,
            'editor_container': None
        }

app_state = AppState()