"""Core engine — pure Python. No HTTP, no GUI, no file dialogs.

The rule: this package must never import from ``api``, ``mcp_server``,
or ``local_agent``. Dependencies point inward only.
"""

from excellia.core.models import Flag, Issue, Profile, ReconcileResult

__all__ = ["Issue", "Flag", "Profile", "ReconcileResult"]
