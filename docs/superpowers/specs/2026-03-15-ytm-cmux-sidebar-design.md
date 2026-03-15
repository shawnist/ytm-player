# ytm-cmux Sidebar Skill Design

## Overview

A global Claude Code skill (`~/.claude/skills/ytm-cmux/`) that displays the currently playing track and next track in the cmux sidebar. A background bash script polls `ytm now` and `ytm queue` every 60 seconds and updates cmux status pills. Auto-cleans up when the Claude Code session exits.

## Skill File

**Location:** `~/.claude/skills/ytm-cmux/skill.md`

**Trigger:** User invokes `/ytm-cmux` or asks to show now-playing in the sidebar.

**Description:** `Use when user wants to show currently playing music in the cmux sidebar, or asks to set up the ytm sidebar display.`

### Behavior on invocation

1. Check if poller is already running via PID file at `$TMPDIR/ytm-cmux-poller.pid`
2. If running: inform user, offer to restart or stop
3. If not running: write the poller script to `$TMPDIR/ytm-cmux-poller.sh`, launch it via `run_in_background` with `dangerouslyDisableSandbox: true`, confirm it started
4. If invoked with `stop` argument: kill the poller, clear pills, remove PID file

## Background Poller Script

**Location:** Written at runtime to `$TMPDIR/ytm-cmux-poller.sh`

### Script logic

```bash
#!/bin/bash

PIDFILE="$TMPDIR/ytm-cmux-poller.pid"
CLAUDE_PID=$PPID

# Write PID file
echo $$ > "$PIDFILE"

# Cleanup function
cleanup() {
    cmux clear-status ytm-now 2>/dev/null
    cmux clear-status ytm-next 2>/dev/null
    rm -f "$PIDFILE"
    exit 0
}

trap cleanup SIGTERM SIGHUP EXIT

while true; do
    # Check if parent Claude session is still alive
    if ! kill -0 "$CLAUDE_PID" 2>/dev/null; then
        cleanup
    fi

    # Get current track (timeout prevents hangs if IPC stalls)
    now=$(timeout 5 ytm now 2>/dev/null)

    if [ -z "$now" ] || [ "$now" = "null" ]; then
        # Nothing playing — clear pills
        cmux clear-status ytm-now 2>/dev/null
        cmux clear-status ytm-next 2>/dev/null
    else
        # Parse now playing
        title=$(echo "$now" | jq -r '.track.title // empty')
        artist=$(echo "$now" | jq -r '.track.artist // empty')

        if [ -n "$title" ]; then
            cmux set-status ytm-now "$title - $artist" \
                --icon music.note --color "#ff2d55"
        fi

        # Get next track from queue
        queue=$(timeout 5 ytm queue 2>/dev/null)
        if [ -n "$queue" ] && [ "$queue" != "null" ]; then
            current_idx=$(echo "$queue" | jq -r '.current_index // 0')
            next_idx=$((current_idx + 1))
            next_title=$(echo "$queue" | jq -r ".tracks[$next_idx].title // empty")
            next_artist=$(echo "$queue" | jq -r ".tracks[$next_idx].artist // empty")

            if [ -n "$next_title" ]; then
                cmux set-status ytm-next "$next_title - $next_artist" \
                    --icon forward.fill --color "#5856d6"
            else
                cmux clear-status ytm-next 2>/dev/null
            fi
        else
            cmux clear-status ytm-next 2>/dev/null
        fi
    fi

    sleep 60
done
```

### Lifecycle

- **Start:** Skill writes script to tmpdir, launches with `run_in_background`
- **Running:** Polls every 60 seconds, updates two cmux status pills
- **Auto-stop:** Checks `kill -0 $PPID` each iteration. When Claude Code exits, PID dies, script detects and runs cleanup
- **Manual stop:** `/ytm-cmux stop` reads PID file, sends SIGTERM, script traps it and cleans up
- **Forced kill:** `trap ... EXIT` ensures cleanup runs regardless of how the script terminates

### `$PPID` reliability (verified)

- In bash, `PPID` is `declare -ir` (readonly integer), set once at shell startup
- Background shells launched by Claude Code have `PPID` pointing to the `claude` binary
- When Claude exits, the PID dies; `kill -0` fails; script exits
- macOS reparents orphans to launchd but `$PPID` variable doesn't change — detection works

## Sidebar Display

| Pill key | Icon | Example content | Color | When shown |
|----------|------|-----------------|-------|------------|
| `ytm-now` | `music.note` | `Becoming Insane - Infected Mushroom` | `#ff2d55` | Track is playing or paused |
| `ytm-next` | `forward.fill` | `Free Tibet - Vini Vici` | `#5856d6` | Next track exists in queue |

Both pills are cleared when nothing is playing.

## Dependencies

- `jq` — JSON parsing in bash
- `cmux` CLI — sidebar status pill management (requires `dangerouslyDisableSandbox: true`)
- `ytm` CLI — track and queue data (requires TUI running; gracefully handles TUI not running)

## Error handling

- TUI not running: `ytm now` returns error → pills cleared, no crash
- `jq` not installed: script fails silently on parse → pills not updated
- cmux not available: `2>/dev/null` suppresses errors, script continues looping
- Multiple invocations: PID file check prevents duplicate pollers

## Files created

| File | Lifecycle |
|------|-----------|
| `$TMPDIR/ytm-cmux-poller.sh` | Written on skill invocation, lives until tmpdir cleanup |
| `$TMPDIR/ytm-cmux-poller.pid` | Written by script on start, removed on cleanup |

## Skill file structure

```
~/.claude/skills/ytm-cmux/
└── skill.md        # Skill definition with instructions for Claude
```

The skill.md instructs Claude to:

### Start flow
1. Check if `$TMPDIR/ytm-cmux-poller.pid` exists and the PID within is alive (`kill -0`)
2. If already running: tell user "ytm sidebar poller is already running (PID X). Want me to restart it?"
3. If not running: write the poller script to `$TMPDIR/ytm-cmux-poller.sh`, launch via Bash tool with `run_in_background: true` and `dangerouslyDisableSandbox: true`
4. Wait 2 seconds, then verify `$TMPDIR/ytm-cmux-poller.pid` exists and PID is alive
5. If verified: tell user "ytm sidebar is live — updates every 60 seconds"
6. If not: tell user "poller failed to start" and show script output for debugging

### Stop flow (argument: `stop`)
1. Read PID from `$TMPDIR/ytm-cmux-poller.pid`
2. If file missing or PID not alive: tell user "poller is not running"
3. If alive: `kill -TERM <PID>` — the script's trap handler clears pills and removes PID file
4. Confirm: "ytm sidebar stopped"

### Restart flow
1. Stop (if running), then Start
