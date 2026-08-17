from __future__ import annotations

import json
from typing import Any

from sqlalchemy.types import UserDefinedType


class VectorType(UserDefinedType):
    """Portable pgvector column type.

    PostgreSQL compiles this as the native ``vector`` extension type. SQLite accepts
    arbitrary type names, which keeps unit tests dependency-free. Values are bound
    as pgvector's textual representation and decoded back to ``list[float]``.
    """

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "vector"

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return value
            return "[" + ",".join(format(float(item), ".17g") for item in value) + "]"
        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None or isinstance(value, list):
                return value
            if isinstance(value, tuple):
                return [float(item) for item in value]
            text = str(value).strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
                return [float(item) for item in parsed]
            except (ValueError, TypeError, json.JSONDecodeError):
                if text.startswith("[") and text.endswith("]"):
                    return [float(item.strip()) for item in text[1:-1].split(",") if item.strip()]
                raise ValueError("invalid vector value returned by database")
        return process
