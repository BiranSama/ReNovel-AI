from nicegui import ui, app
from src.di.container import Container, get_container
from src.infrastructure.database import Database, db
from src.infrastructure.database.repositories.project_repo import SQLiteProjectRepository
from src.infrastructure.database.repositories.chapter_repo import SQLiteChapterRepository
from src.application.services import ProjectService, ChapterService
from src.interfaces import app_state
from config.settings import settings


def init_container() -> Container:
    container = get_container()
    
    container.register_instance(Database, db)
    
    container.register_factory(
        SQLiteProjectRepository,
        lambda c: SQLiteProjectRepository(c.resolve(Database)),
        singleton=True
    )
    
    container.register_factory(
        SQLiteChapterRepository,
        lambda c: SQLiteChapterRepository(c.resolve(Database)),
        singleton=True
    )
    
    container.register_factory(
        ProjectService,
        lambda c: ProjectService(
            c.resolve(SQLiteProjectRepository),
            c.resolve(SQLiteChapterRepository)
        ),
        singleton=True
    )
    
    container.register_factory(
        ChapterService,
        lambda c: ChapterService(
            c.resolve(SQLiteChapterRepository)
        ),
        singleton=True
    )
    
    return container


async def init_database():
    async with db.connection() as conn:
        pass


def create_ui():
    from src.interfaces.views.layouts.main_layout import create_layout
    create_layout()


def main():
    container = init_container()
    
    app.on_startup(init_database)
    
    ui.page_title('Re:Novel AI')
    
    create_ui()
    
    ui.run(
        title="Re:Novel AI",
        port=settings.server_port,
        reload=settings.debug,
        dark=False
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
