# Active Context

## Current Focus
Membership system refactored to bypass remote verification; local users now default to unlimited runtime.

## Recent Events
- 2026-07-12: Merge `upstream/HEAD` / `upstream/main` updates up to `ae4aa12` into `develop`: fix large-event reward collection hanging on the lobby page, and sync MaaFramework Project Interface schema updates. Preserve local membership bypass in `agent/go-service/taskersink/membership/memberdata.go`.
- 2026-07-02: Merge `upstream/HEAD` / `upstream/main` updates up to `3f59e62` (v1.7.8) into `develop`: v1.7.4-v1.7.8 large-event WAVE TO YOU support and mini-game adaptation, large-event mission reward threshold/flow fixes, mold-opening flow optimization, simulation-room overclock recognition region adjustment, ADB resolution limit relaxation, user config storage path adjustment, recycling-shop click delay update, README updates, and related locale/image/pipeline updates. Resolve recycle-room upgrade conflict by preserving the local click-flow orchestration while keeping upstream availability color check. Preserve local membership bypass in `agent/go-service/taskersink/membership/memberdata.go`.
- 2026-06-26: Merge `upstream/HEAD` / `upstream/main` updates up to `d7c4bd8` (v1.7.3) into `develop`: v1.7.2/v1.7.3 membership quota prompt improvements, battle auto-node merge and Boss animation auto-skip, ArkRanger hard-stage adaptation, event reward/minigame flow fixes, recycle-room upgrade optimization, profile red-dot clearing, advise template threshold update, and image/template updates. Preserve local membership bypass in `agent/go-service/taskersink/membership/memberdata.go`.
- 2026-06-23: Merge `upstream/HEAD` / `upstream/main` update `1527a10` into `develop`: adjust advise recognition expected content. Preserve local membership bypass in `agent/go-service/taskersink/membership/memberdata.go`.
- 2026-06-20: Merge `upstream/HEAD` / `upstream/main` updates up to `638383b` (v1.7.1) into `develop`: lucky-box opening task, arcade red-dot clearing, membership verification unavailable handling, battle/event/account-nurturing fixes, and image/template updates. Preserve local membership bypass in `agent/go-service/taskersink/membership/memberdata.go`.
- 2026-06-16: Sync `upstream/main` updates up to `94f2fe9` (v1.6.5) into `develop`: activity region popup/text fixes, mini-game return flow, arena cumulative reward click limit, free-state confirmation, cash-shop collection, battle entry text, badge sticker offset, and locale/preset cleanup. Preserve local membership bypass, Memory Bank, and CI guards.
- 2026-06-13: Sync `upstream/main` updates up to `ec4ed53` into `develop`, including ArkRanger mini-game option, activity-option switches, preset cleanup, and project refactor. Push `v3.0.2` release; CI passes for all platforms.
- 2026-06-12: Merge `upstream/main` v1.6.2 into `develop`; preserve local membership bypass and Memory Bank. Push `v3.0.1` release; CI passes for all platforms.
- 2026-06-07: Refactor membership `checkMembership()` to return local unlimited status without network calls or device-code generation.
- 2025-06-06: Initialize Memory Bank with 7 core files based on existing codebase analysis.

## Active Decisions
- **No remote membership verification**: `checkMembership()` now short-circuits to a fixed `UnlimitedRuntime: true` status. Existing quota/refill/device-code code remains in repo but is effectively unreachable in normal flow.
- **Membership bypass is non-negotiable**: Disabling remote membership verification is the primary purpose of this fork. Any upstream sync, merge, or refactor must preserve the bypass in `agent/go-service/taskersink/membership/memberdata.go`. If upstream changes threaten this, the local bypass wins.
- **develop branch**: Active feature branch created from `main` for this refactor.

## Blockers
- None.

## Next Steps
1. Monitor for any side effects from bypassing quota enforcement (e.g., unexpected `membership-quota.json` writes).
2. If needed later, clean up unreachable code (device-code generation, HTTP fetch, refill logic, tests).
3. Keep memory bank in sync with future feature additions or refactors.
