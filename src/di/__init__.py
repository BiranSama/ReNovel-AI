from src.di.container import Container, container

__all__ = [
    "Container",
    "container",
]


def get_container() -> Container:
    return container
