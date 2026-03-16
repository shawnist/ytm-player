"""cmux sidebar integration — posts now-playing info to cmux status pills.

Only activates when CMUX_WORKSPACE_ID is set in the environment and the
cmux binary is available on PATH.  All operations are fire-and-forget;
failures are logged at debug level and never raised.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil

logger = logging.getLogger(__name__)


class CmuxService:
    """Thin wrapper around ``cmux set-status`` / ``cmux clear-status``."""

    def __init__(self) -> None:
        self._workspace = os.environ.get("CMUX_WORKSPACE_ID", "")
        self._cmux_bin = shutil.which("cmux") or ""
        if self._workspace and self._cmux_bin:
            logger.info("cmux sidebar integration active (workspace %s)", self._workspace)
        else:
            logger.debug("cmux sidebar integration inactive")

    @property
    def is_available(self) -> bool:
        return bool(self._workspace and self._cmux_bin)

    async def update(
        self,
        title: str,
        artist: str,
        next_title: str | None = None,
        next_artist: str | None = None,
    ) -> None:
        """Set the now-playing and up-next sidebar pills."""
        if not self.is_available:
            return

        now_label = f"{title} - {artist}" if artist else title

        # Set ytm-now first so it appears above ytm-next in the sidebar.
        await self._set_status("ytm-now", now_label, icon="music.note", color="#ff2d55")

        if next_title:
            next_label = f"{next_title} - {next_artist}" if next_artist else next_title
            await self._set_status("ytm-next", next_label, icon="forward.fill", color="#5856d6")
        else:
            await self._clear_status("ytm-next")

    async def clear(self) -> None:
        """Clear both sidebar pills."""
        if not self.is_available:
            return
        await self._clear_status("ytm-now")
        await self._clear_status("ytm-next")

    async def _set_status(self, key: str, value: str, icon: str, color: str) -> None:
        await self._run(
            self._cmux_bin,
            "set-status",
            key,
            value,
            "--icon",
            icon,
            "--color",
            color,
            "--workspace",
            self._workspace,
        )

    async def _clear_status(self, key: str) -> None:
        await self._run(
            self._cmux_bin,
            "clear-status",
            key,
            "--workspace",
            self._workspace,
        )

    async def _run(self, *cmd: str) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=3)
        except Exception:
            logger.debug("cmux command failed: %s", " ".join(cmd), exc_info=True)
