"""Bug reporter destinations: where bugs ultimately end up."""
from .helpdesk import publish as publish_to_helpdesk
from .github import publish as publish_to_github

__all__ = ["publish_to_helpdesk", "publish_to_github"]
