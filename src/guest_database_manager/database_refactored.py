"""Compatibility entry point for the refactored database implementation.

The application now keeps the production implementation in :mod:`database`,
but older launchers and integrations still import ``database_refactored``.
Keeping this thin alias avoids maintaining two divergent database classes.
"""

try:
    from .database import GuestDatabase
except ImportError as exc:
    if "attempted relative import" not in str(exc):
        raise
    from database import GuestDatabase

__all__ = ["GuestDatabase"]
