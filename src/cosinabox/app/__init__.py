"""cosinabox.app — re-exports for backward compatibility."""

from cosinabox.app._core import _FRONTMATTER_RE, App
from cosinabox.app.chat import is_approval

__all__ = ["App", "is_approval", "_FRONTMATTER_RE"]
