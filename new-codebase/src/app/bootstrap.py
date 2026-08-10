from functools import lru_cache

from app.orchestration.root_graph import create_root_graph


@lru_cache
def get_graph():
    return create_root_graph()

