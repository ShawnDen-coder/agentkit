"""Protocol helpers: deterministic IDs and SSE serialization utilities."""

from __future__ import annotations

import xxhash


__all__ = ["deterministic_uuid"]


def deterministic_uuid(origin: str, component_id: str) -> str:
    """Stable cross-turn component UUID: ``xxhash(origin + component_id)``.

    Determinism lets the frontend reconcile the same component across FunctionCall
    loop round-trips (§4.1). Same inputs -> same UUID, forever, across processes.
    """
    h = xxhash.xxh64()
    h.update(f"{origin}:{component_id}".encode())
    return h.hexdigest()
