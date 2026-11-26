"""Compatibility shim: allows `uvicorn backend.app:app` from repo root."""

try:
    from .main import app  # noqa: F401
except Exception:  # pragma: no cover - fallback for script-style execution
    from main import app  # type: ignore  # noqa: F401

