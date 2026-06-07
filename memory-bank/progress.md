# Progress

## What Works
- Full MXU frontend integration with Project Interface v2.
- 17+ task definitions covering daily, periodic, and event gameplay loops.
- 3 preset task combinations (`DailyFull`, `QuickDaily`, `SelfUse`).
- Win32 controller support (Background, PrintWindow, ScreenDC) + ADB.
- Go agent with custom sinks:
  - `aspectratio` — display aspect ratio validation
  - `hdrcheck` — Windows HDR state detection
  - `processcheck` — NIKKE process validation
  - `membership` — quota / device-code / refill logic
- Localization for `zh_cn` and `en_us`.
- Comprehensive pipeline naming conventions documented in `docs/pipeline-node-naming.md`.
- Issue log analysis skill set up for debugging.

## What's Left
- Ongoing game version adaptation (new UI flows, new events).
- Potential new task domains as game content expands.
- Go agent sink expansion if new environmental checks are needed.
- Continuous locale synchronization when adding tasks/options.

## Current Status
Stable, actively maintained. Memory bank initialized to improve cross-session agent context.

## Known Issues
- Script recognition is **CN-only**; non-Chinese game clients will fail.
- Debug image generation can consume significant disk space if left on for long runs.
- Free tier limited to 10 minutes/day (by design, not a bug).

## Evolution of Decisions
- Originally `DoroHelper`; rewritten as MDA on MaaFramework for better maintainability.
- Membership model shifted from gating specific tasks to a unified daily runtime quota.
- Node naming moved away from `FlagInX` style to explicit `On...Page` / `Visible` / `Entered` semantics.
