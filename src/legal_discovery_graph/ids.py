"""Deterministic identifier minting for reproducible generation.

`models.py` defaults to random uuid4 IDs for runtime use; generated corpora
instead mint uuid5 IDs from stable key parts so the same seed always produces
byte-identical output (a Milestone 1 exit criterion).
"""

from uuid import NAMESPACE_URL, uuid5

_NAMESPACE_PREFIX = "legal-discovery-graph"


def stable_id(*parts: object) -> str:
    """Return a deterministic 32-char hex ID derived from the given key parts."""
    key = ":".join(str(part) for part in parts)
    return uuid5(NAMESPACE_URL, f"{_NAMESPACE_PREFIX}:{key}").hex
