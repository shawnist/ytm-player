"""Command Center integration — posts now-playing info via CC status pill API.

Activates when CC_WORKSPACE_ID is set. Takes priority over cmux when active,
since CC_WORKSPACE_ID is explicitly set by the Command Center server when
launching panes.

All operations are fire-and-forget; failures are logged at debug level.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Known location of the cc.py CLI
_CC_PY = Path.home() / "Projects" / "command-center" / "cc.py"


class CommandCenterService:
    """Publish now-playing pills via ``uv run cc.py``."""

    def __init__(self) -> None:
        self._workspace = os.environ.get("CC_WORKSPACE_ID", "")
        self._cc_py = str(_CC_PY) if _CC_PY.is_file() else ""

        if self._workspace and self._cc_py:
            logger.info("Command Center integration active (workspace %s)", self._workspace)
        else:
            logger.debug("Command Center integration inactive (workspace=%s, cc.py=%s)",
                         self._workspace, self._cc_py)

    @property
    def is_available(self) -> bool:
        return bool(self._workspace and self._cc_py)

    async def update(
        self,
        title: str,
        artist: str,
        next_title: str | None = None,
        next_artist: str | None = None,
    ) -> None:
        """Set the now-playing and up-next pills."""
        if not self.is_available:
            return

        now_label = f"{title} - {artist}" if artist else title
        await self._set_status("ytm-now", now_label, icon="music.note", color="#ff2d55")

        if next_title:
            next_label = f"{next_title} - {next_artist}" if next_artist else next_title
            await self._set_status("ytm-next", next_label, icon="forward.fill", color="#5856d6")
        else:
            await self._clear_status("ytm-next")

    async def clear(self) -> None:
        """Clear both pills."""
        if not self.is_available:
            return
        await self._clear_status("ytm-now")
        await self._clear_status("ytm-next")

    async def _set_status(self, key: str, value: str, icon: str, color: str) -> None:
        await self._run("set-status", self._workspace, key, value, "--icon", icon, "--color", color)

    async def _clear_status(self, key: str) -> None:
        await self._run("clear-status", self._workspace, key)

    async def _run(self, *args: str) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "uv", "run", "--project", str(_CC_PY.parent), self._cc_py, *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=5)
        except Exception:
            logger.debug("cc command failed: %s", " ".join(args), exc_info=True)
