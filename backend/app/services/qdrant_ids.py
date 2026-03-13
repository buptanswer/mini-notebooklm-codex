from uuid import NAMESPACE_URL, uuid5


def qdrant_point_id_for_child(child_chunk_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, child_chunk_id))
