"""Screen administration uses the same authentication as all private routes."""
from app.core.auth import require_admin as require_admin_network

__all__ = ["require_admin_network"]
