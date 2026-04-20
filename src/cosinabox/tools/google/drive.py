"""Google Drive tool — minimal search + file fetch.

Small on purpose: the only in-tree caller is the commitment verifier
(`cosinabox.commitments.auto_resolve`). Treat this as scaffolding; grow
the surface when a second caller needs it.

Auth: reuses the existing Google OAuth credentials. Drive API calls
require the `drive.readonly` scope — minted refresh tokens without it
will 403 on every call; the tool catches that and returns empty so
downstream callers aren't surprised by a crash.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

try:
    from googleapiclient.discovery import Resource, build  # type: ignore[import-untyped]
    from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
except ImportError as e:
    raise ImportError(
        "cosinabox[google] extra is required. Run: pip install 'cosinabox[google]'"
    ) from e

from cosinabox.tools.google.auth import build_all_credentials

logger = logging.getLogger(__name__)


@dataclass
class DriveFile:
    id: str
    name: str
    mime_type: str
    modified_time: str
    web_view_link: str


def _q_quote(value: str) -> str:
    """Escape a string for Drive `fullText contains '<value>'` queries.

    Backslashes first, then single quotes — single-quote before backslash
    would double-escape.
    """
    return value.replace("\\", "\\\\").replace("'", "\\'")


class DriveTool:
    def __init__(
        self,
        *,
        service: Resource | None = None,
        services: list[Resource] | None = None,
    ) -> None:
        if services is not None:
            self._services = services
        elif service is not None:
            self._services = [service]
        else:
            self._services = [
                build("drive", "v3", credentials=cred) for cred in build_all_credentials()
            ]

    def search(self, query: str, *, max_results: int = 10) -> list[DriveFile]:
        """Return files whose content or name contains ``query`` across all
        configured accounts. Dedupes by file id. Sorted by modifiedTime
        descending. Returns an empty list if the Drive scope isn't granted.
        """
        if not query:
            return []
        safe = _q_quote(query)
        q = f"fullText contains '{safe}' and trashed = false"

        seen: set[str] = set()
        out: list[DriveFile] = []
        for svc in self._services:
            try:
                resp = (
                    svc.files()
                    .list(
                        q=q,
                        pageSize=max_results,
                        fields="files(id, name, mimeType, modifiedTime, webViewLink)",
                        orderBy="modifiedTime desc",
                    )
                    .execute()
                )
            except HttpError as exc:
                status = getattr(getattr(exc, "resp", None), "status", "?")
                logger.warning(
                    "drive.search HTTP %s for query=%r — likely missing drive.readonly scope",
                    status,
                    query,
                )
                continue
            except Exception:
                logger.debug("drive.search transient error", exc_info=True)
                continue
            for f in resp.get("files", []):
                fid = f.get("id")
                if not fid or fid in seen:
                    continue
                seen.add(fid)
                out.append(
                    DriveFile(
                        id=fid,
                        name=f.get("name", ""),
                        mime_type=f.get("mimeType", ""),
                        modified_time=f.get("modifiedTime", ""),
                        web_view_link=f.get("webViewLink", ""),
                    )
                )
        out.sort(key=lambda f: f.modified_time, reverse=True)
        return out[:max_results]

    def get_file_metadata(self, file_id: str) -> dict[str, Any] | None:
        """Return raw metadata for a single file (if any account can see it).

        None if no account has access — 403 is treated the same as 404.
        """
        for svc in self._services:
            try:
                result = (
                    svc.files()
                    .get(
                        fileId=file_id,
                        fields="id, name, mimeType, modifiedTime, webViewLink",
                    )
                    .execute()
                )
            except HttpError:
                continue
            except Exception:
                logger.debug("drive.get_file_metadata error", exc_info=True)
                continue
            return dict(result)
        return None
