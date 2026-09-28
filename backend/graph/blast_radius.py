"""Blast radius: transitive dependents of a resource (BFS)."""

from collections import deque


def blast_radius(graph: dict[str, list[str]], start_id: str) -> list[str]:
    """Return every resource that transitively depends on start_id, in BFS order.

    graph maps a resource id to the ids of resources that depend on it.
    start_id itself is never included, even if the graph has a cycle.
    """
    seen = {start_id}
    order: list[str] = []
    queue = deque([start_id])
    while queue:
        for dep in graph.get(queue.popleft(), []):
            if dep not in seen:
                seen.add(dep)
                order.append(dep)
                queue.append(dep)
    return order
