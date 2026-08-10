from langgraph.checkpoint.memory import InMemorySaver


def create_checkpointer() -> InMemorySaver:
    """Development checkpointer; replace this provider for production storage."""
    return InMemorySaver()
