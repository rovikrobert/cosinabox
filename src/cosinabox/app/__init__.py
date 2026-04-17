"""cosinabox.app — re-exports for backward compatibility."""

from cosinabox.app._core import App
from cosinabox.app.chat import is_approval
from cosinabox.app.config import _FRONTMATTER_RE

__all__ = ["App", "is_approval", "_FRONTMATTER_RE"]
