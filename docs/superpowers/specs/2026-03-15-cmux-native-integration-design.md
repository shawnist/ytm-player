# cmux Native Sidebar Integration Design

## Overview

Add a `CmuxService` to ytm-player that posts now-playing and up-next track info to the cmux sidebar whenever a track changes or playback stops. Only activates when `CMUX_WORKSPACE_ID` is set in the environment. Replaces the external polling script approach.

## Service: `CmuxService`

**File:** `src/ytm_player/services/cmux.py`

A thin wrapper around `cmux set-status` / `cmux clear-status` CLI calls.

### Interface

```python
class CmuxService:
    def __init__(self) -> None:
        """Capture CMUX_WORKSPACE_ID from env. Set is_available=False if not set or cmux not found."""

    @property
    def is_available(self) -> bool:
        """True if CMUX_WORKSPACE_ID is set and cmux binary exists on PATH."""

    async def update(self, title: str, artist: str, next_title: str | None, next_artist: str | None) -> None:
        """Set ytm-now pill, then ytm-next pill (order matters — now-playing appears above next-up)."""

    async def clear(self) -> None:
        """Clear both ytm-now and ytm-next pills."""
```

### Implementation details

- Store `workspace_id` from `os.environ.get("CMUX_WORKSPACE_ID")`
- Check for `cmux` binary with `shutil.which("cmux")` at init time
- If either is missing, `is_available` returns False and all methods are no-ops
- Run `cmux set-status` / `cmux clear-status` via `asyncio.create_subprocess_exec` to avoid blocking
- Always pass `--workspace <workspace_id>` explicitly
- Set `ytm-now` before `ytm-next` so now-playing pill appears above up-next in the sidebar
- Suppress all errors — cmux integration should never crash the player

### Pill configuration

| Pill key | Icon | Color | Content | Order |
|----------|------|-------|---------|-------|
| `ytm-now` | `music.note` | `#ff2d55` | `{title} - {artist}` | First (top) |
| `ytm-next` | `forward.fill` | `#5856d6` | `{title} - {artist}` | Second (below) |

## Integration points

### 1. App initialization (`_app.py` → `on_mount`)

After other optional services (Discord, Last.fm):

```python
self.cmux = CmuxService()
```

No conditional import needed — the service is always available, it just no-ops when not in cmux.

### 2. Track starts playing (`_playback.py` → `play_track()`)

After the existing Discord/Last.fm/MPRIS updates (around line 170):

```python
if self.cmux and self.cmux.is_available:
    next_track = self.queue.peek_next()
    await self.cmux.update(
        title=track.get("title") or "",
        artist=track.get("artist") or "",
        next_title=next_track.get("title") if next_track else None,
        next_artist=next_track.get("artist") if next_track else None,
    )
```

### 3. Track ends / playback stops (`_playback.py` → `_on_track_end()`)

When queue is exhausted and no more tracks to play, clear the pills. This happens when `_play_next()` returns without starting a new track. The simplest approach: the pills get re-set on each `play_track()` call, and cleared in shutdown. If the queue ends naturally, the last track's pill stays until shutdown — which is acceptable since it shows what was last played.

Alternatively, add a clear in the `_on_track_end` path when no next track exists:

```python
if self.cmux and self.cmux.is_available:
    if not self.queue.peek_next() and self.queue.repeat_mode == "off":
        await self.cmux.clear()
```

### 4. App shutdown (`_app.py` → `on_unmount`)

Clear pills on exit so the sidebar doesn't show stale data:

```python
if self.cmux and self.cmux.is_available:
    await self.cmux.clear()
```

## What this replaces

- The `~/.claude/skills/ytm-cmux/` skill (background poller script)
- The post-DJ sidebar update block in `~/.claude/skills/ytm/skill.md`
- The `$TMPDIR/ytm-cmux-poller.sh` and `.pid` files

The `ytm-cmux` skill should be updated to simply state that cmux integration is built into the player and activates automatically when `CMUX_WORKSPACE_ID` is set.

## Testing

- No unit tests needed for this — it's a fire-and-forget subprocess wrapper with no return values
- Manual testing: run `ytm` inside cmux, play a track, verify pills appear; skip tracks, verify pills update; quit ytm, verify pills clear
- Test without cmux: run `ytm` outside cmux, verify no errors

## Error handling

- All subprocess calls wrapped in try/except — failures logged at debug level, never raised
- Missing `cmux` binary detected at init, not at call time
- Missing `CMUX_WORKSPACE_ID` detected at init
- Subprocess timeouts: use a 3-second timeout on `asyncio.create_subprocess_exec` to prevent hangs
