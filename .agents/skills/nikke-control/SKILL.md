---
name: nikke-control
description: Observe and control the Windows NIKKE client through an on-demand AAA CLI session, including single-encounter campaign battle delegation. Use for live game interaction; not for changing MDA task pipelines.
---

# NIKKE Control CLI

Use `E:\Git\MDA\tools\nikke_cli.py`. The CLI uses the existing AAA controller (`ScreenDC`, `Interception`, `Seize`) without an MCP dependency. Start a control session only when the user's task requires live game interaction. Reading this skill, opening a chat, or checking the environment must not launch a control session or request UAC.

## Start only when needed

For read-only diagnostics, run these commands without a session or UAC:

```powershell
python E:\Git\MDA\tools\nikke_cli.py status
python E:\Git\MDA\tools\nikke_cli.py windows
```

For actual game control, start one managed terminal session:

```powershell
python -u E:\Git\MDA\tools\nikke_cli.py session
```

Use `exec_command` with `tty: true`, retain its `session_id`, and wait for `{"ok": true, "session": "ready"}`. The CLI requests Windows UAC once for its control worker; Codex keeps its current privileges. Cancellation stops startup rather than retrying. Reuse this session across actions. Do not start another process for each click or observation.

`session --no-elevate` inherits current privileges for diagnostics; it does not solve an elevated game's permission requirements. A different MaaFramework directory can be supplied before the command with `--maa-dir <absolute-directory>`.

## Send commands and inspect images

Send one command plus a newline through `write_stdin` using the retained terminal session ID. Every reply is a JSON line; the terminal may also echo commands and ANSI control codes. Both shell-style commands and JSON requests are accepted:

```text
connect
{"op":"connect","window_id":"0x12345"}
observe
observe --wait-ms 1000
click 640 360 --snapshot <latest-snapshot-id> --wait-ms 800
drag 900 400 400 400 --duration-ms 600 --snapshot <latest-snapshot-id>
key escape --snapshot <latest-snapshot-id>
key escape --snapshot <latest-snapshot-id> --no-screenshot
battle --snapshot <latest-snapshot-id>
status
stop
windows
quit
```

Use actual returned IDs and observed coordinates. `connect` selects a window only when there is one candidate; otherwise use `windows`, then `connect --window-id <id>`. JSON uses the controller parameter names, for example `{"op":"click","snapshot_id":"...","x":640,"y":360}`.

`connect`, `observe`, and successful inputs normally return an absolute `image_path`, a new `snapshot_id`, image dimensions, original dimensions, capture time and `image_changed`. Screenshots replace one `latest.png` per session. Inspect one image for each decision before requesting the next capture.

When optional Pillow is available, the CLI also returns `preview_path` if its same-size JPEG is smaller than the PNG. Prefer `view_image(preview_path)`; otherwise open `image_path`. This happens in the same reply, without another capture or tool call. If small text is unclear, inspect the original PNG; do not load both versions routinely. The original `snapshot_id` and coordinates apply to either image. A session keeps one `latest.preview.jpg` beside its PNG. Without Pillow, all control commands still work.

For an older local screenshot, this read-only command can create the same preview outside the managed session:

```powershell
python E:\Git\MDA\tools\nikke_cli.py preview '<returned-image_path>'
```

`preview` returns the JPEG's `image_path` and byte counts. It does not connect, request UAC or capture again. Do not run it separately when the session already returned `preview_path`.

Reduce image traffic at its source:

- When an action starts travel or an animation, use `--wait-ms N` on `click`, `drag` or `key` to wait after input and capture only once. `observe --wait-ms N` waits before observation. The range is 0–10000 ms; choose a bounded delay from the actual transition, not a fixed delay for every action.
- Use `--no-screenshot` for an action whose immediate frame is only an expected transition. It returns `observation_status: skipped` without an image or new snapshot. The old snapshot is consumed: wait, then `observe` and inspect before another input. JSON equivalents are `wait_ms` and `capture: false`. These options do not apply to `battle`.
- `image_changed: false` means the PNG bytes exactly match the previous published capture. If that image was already inspected and remains in context, skip both preview and `view_image`; the new snapshot is usable with the same visible contents. This does not prove input failed or the game is idle. If the previous image was never inspected or its context is missing, view the latest image once.
- Keep `status`/battle waits text-only. Reuse an action's settled image instead of immediately sending `observe` again. Keep navigation progress in compact text using landmarks, stage IDs and pending decisions.

Overwriting a local image does not remove images already attached to chat history. JPEG reduces upload bytes; unchanged pixel dimensions do not guarantee fewer vision tokens. This CLI cannot prune the host conversation. Long runs still depend on the host's context compaction; never edit chat history files to remove screenshots.

Coordinates belong to the returned image. The framework scales the long edge to 1280 and maps input back to the window; do not apply desktop offsets or another DPI/resolution conversion. A standard landscape image is 1280×720.

Each input, including battle delegation, must name the latest observed `snapshot_id`. The controller consumes it before submission. Window identity/geometry changes, lost focus, and obstructed points require a new observation, not blind retries. `observe` restores and activates the game; an input does not activate the window and then click old coordinates. Do not run MDA tasks against the same window concurrently.

## Delegate one campaign encounter

Use `battle --snapshot <id>` (JSON: `{"op":"battle","snapshot_id":"..."}`) after inspecting a Normal/Hard main-story preparation page and choosing to fight this non-EX encounter. Preserve the current formation. The local MDA Pipeline prefers quick battle, otherwise enters normal auto-battle, skips story, handles known result/reward dialogs and returns to the map or a chapter-transition prompt. It does not choose another enemy, change formation, use MAX, advance to the next stage or retry defeat. If the user wants to read story, use manual commands for this encounter because battle currently skips it.

The first reply acknowledges acceptance with `op: battle`, `battle_id`, `status: running`. It is not completion. Resource/Tasker loading occurs only on the first battle in this connection and reuses the current Controller and UAC authorization. While battle owns the Controller, only `status` and `stop` are allowed. Do not send `observe`, clicks, reconnect/disconnect or another battle.

Wait for `type: battle.finished` with the same `battle_id` through empty `write_stdin` polls, using bounded waits of at most 60 seconds. These are terminal waits; no repeated screenshot reasoning or battle button handling is needed. `status` reports phase, owner and the latest result without capturing. Send `stop` when interrupted or intervention is required; `status: stopping` only acknowledges the request. A `battle.stopping` event with `reason: stop_pending` is not completion: keep waiting while ownership remains isolated. `quit` is rejected until completion.

For the final event, read the fields separately:

- `status`: `completed`, `blocked`, `timed_out`, `cancelled` or `failed` describes execution/handoff.
- `outcome`: currently `lost`, `unknown` or `not_started`. No positive victory recognition has been validated; ESC, Tasker success and map visibility never become `won`. Do not repeat a battle merely because outcome is unknown.
- `return_state` and `controller_idle`: continue only after the Controller is idle; inspect the returned `image_path` to confirm the actual map and enemy change. A chapter prompt leaves chapter decisions to the caller. A normal defeat returned to the map can have `ok: true`.
- Capture/save failure preserves the encounter outcome and input status. Once idle, observe again without replaying battle.

The total battle deadline is 300 seconds; loading has a 30-second limit. Stop/focus-change monitoring cannot retract already queued input. A lost-focus or geometry-change result may report `input_status: unknown`; wait for actual idle, observe and re-evaluate. Virtual-controller replays cover routing and stopping; first live use still needs game acceptance checks.

## Interpret results and close the session

- `input_status: not_sent`: no input was submitted; resolve the reported condition.
- `input_status: completed`: the framework finished the input; inspect the new image to verify the game's response.
- `input_status: unknown`: the input may have partly executed. Do not repeat it; wait for any pending request and observe again.
- `observation_status: failed` after a completed input: capture or image saving failed, not the input. Observe again without replaying it.
- `observation_status: skipped`: capture was explicitly omitted; observe and inspect before the next input.

For manual interaction, prefer one delayed capture after an animation; use another bounded observation only if the returned frame still shows a transition. During delegated battle the local Tasker captures internally; only the final image is published.

When the requested work finishes or fails, stop any active battle and wait for `battle.finished`, then send `quit\n` and confirm `session: closed` and terminal process exit, unless the user explicitly requested keeping control open. `disconnect` releases Tasker/Resource before the Controller while keeping the CLI alive; `quit` ends the CLI too. A pending native request blocks `quit`; check status and retry cleanup after the request settles. EOF requests battle stop and waits for native cleanup; `session: cleanup_pending` is not a closed session. Forced process termination cannot guarantee native cleanup.

The CLI itself does not need uv or third-party Python packages. It reuses the anonymous-pipe elevation helper in `tools/nikke_mcp_launcher.py`; that filename does not mean MCP is started. Worker logs are under `E:\Git\MDA\.cache\nikke-control\elevated-stderr.log`.
