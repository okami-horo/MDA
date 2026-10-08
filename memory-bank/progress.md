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
  - `membership` — quota / device-code / refill logic (bypassed in this fork; local unlimited)
- Localization for `zh_cn` and `en_us`.
- Comprehensive pipeline naming conventions documented in `docs/pipeline-node-naming.md`.
- Issue log analysis skill set up for debugging.

## What's Left

- Ongoing game version adaptation (new UI flows, new events).
- Potential new task domains as game content expands.
- Go agent sink expansion if new environmental checks are needed.
- Continuous locale synchronization when adding tasks/options.
- Update project docs and Memory Bank when upstream adds significant features.

## Current Status

Stable, actively maintained. Remote membership verification disabled on `develop` branch; all users now run with unlimited runtime. **Preserving the membership bypass is the top priority for every future change, including upstream merges.** As verified on 2026-10-08, `upstream/HEAD` is synchronized through `e5ab2b9` (v1.10.11), preserving the local unlimited membership status, quota-state I/O guards, and `QuickBattleAvailable.count=80`. The latest sync adds LITTLE WITCH TRICK SmallEvent support and updates Simulation Room and sudden-story UI handling; Go code is unchanged. The new locale key is appended in both languages to preserve existing order. Theme routing, JSONC parsing, node/option/group/locale/template references, ROI bounds, preserved past themes, locale parity/order, PNG dimensions/decompression, and whitespace checks passed. Full Schema validation is unavailable without Python, and game validation remains pending. See [activeContext.md](activeContext.md) for sync details and earlier integration decisions.

## Known Issues

- Script recognition is **CN-only**; non-Chinese game clients will fail.
- Debug image generation can consume significant disk space if left on for long runs.
- ~~Free tier limited to 10 minutes/day (by design, not a bug).~~ **Removed**: remote membership verification bypassed; all local users default to unlimited runtime.

## Evolution of Decisions

- Originally `DoroHelper`; rewritten as MDA on MaaFramework for better maintainability.
- Membership model shifted from gating specific tasks to a unified daily runtime quota.
- Node naming moved away from `FlagInX` style to explicit `On...Page` / `Visible` / `Entered` semantics.
- **2026-06-07**: Remote membership verification bypassed entirely. `checkMembership()` short-circuits to local unlimited status. Quota enforcement code preserved in repo but no longer active.
- **2026-07-11**: Runtime log `task_id=200000137` confirmed that quick-battle OCR succeeded, but `QuickBattleAvailable` detected 98 near-white pixels against a threshold of 100, causing fallback to normal battle. Lowered `assets/resource/pipeline/Battle/Battle.json` `QuickBattleAvailable.count` to 80 and passed Pipeline/Interface schema validation; real-game validation of both available and unavailable quick-battle states remains pending.
