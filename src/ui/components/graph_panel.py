"""人物关系图谱：力导向图展示，可增量更新（只分析内容有变化的章节）。"""
from nicegui import ui


class GraphPanel:
    def __init__(self, session):
        self.session = session
        with ui.row().classes('w-full p-2 border-b bg-gray-50 justify-between items-center'):
            ui.label('关系网').classes('text-xs font-bold text-gray-500')
            with ui.row().classes('gap-1'):
                ui.button('增量更新', on_click=session.update_graph_incrementally).props('flat dense icon=update color=indigo')
                ui.button('刷新', on_click=session.refresh_graph_ui).props('flat dense icon=refresh')
        self.chart = ui.echart({'series': [{'type': 'graph', 'layout': 'force', 'data': [], 'links': []}]}) \
            .classes('w-full flex-grow')
        session.graph_view = self

    def show(self, engine):
        data = engine.get_visualization_data()
        if not data['nodes']: return
        series = self.chart.options['series'][0]
        series['data'], series['links'] = data['nodes'], data['links']
        self.chart.update()
