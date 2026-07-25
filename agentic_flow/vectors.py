from __future__ import annotations

import hashlib
import math
import re
from typing import Any


WORD = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)
EMBEDDING_DIMENSIONS = 256


def embed_text(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Create a deterministic local embedding without an external AI service."""
    vector = [0.0] * dimensions
    tokens = [token.lower() for token in WORD.findall(text)]
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = -1.0 if digest[4] & 1 else 1.0
        vector[bucket] += sign
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude:
        vector = [value / magnitude for value in vector]
    return vector


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    normalized = re.sub(r"\r\n?", "\n", text).strip()
    if not normalized:
        return []
    size = max(100, min(int(size), 8000))
    overlap = max(0, min(int(overlap), size - 1))
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        if end < len(normalized):
            boundary = max(
                normalized.rfind("\n", start + size // 2, end),
                normalized.rfind(" ", start + size // 2, end),
            )
            if boundary > start:
                end = boundary
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks


def documents_from_value(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        return [{"text": value, "metadata": {}}]
    if isinstance(value, dict):
        if "text" in value or "content" in value:
            return [
                {
                    "text": str(value.get("text") or value.get("content") or ""),
                    "metadata": dict(value.get("metadata") or {}),
                }
            ]
        return [{"text": str(value), "metadata": {}}]
    if isinstance(value, list):
        documents: list[dict[str, Any]] = []
        for item in value:
            documents.extend(documents_from_value(item))
        return documents
    return [{"text": str(value), "metadata": {}}]

