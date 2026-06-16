# Active Context

## Current Focus
Membership system refactored to bypass remote verification; local users now default to unlimited runtime.

## Recent Events
- 2026-06-13: Sync `upstream/main` updates up to `ec4ed53` into `develop`, including ArkRanger mini-game option, activity-option switches, preset cleanup, and project refactor. Push `v3.0.2` release; CI passes for all platforms.
- 2026-06-12: Merge `upstream/main` v1.6.2 into `develop`; preserve local membership bypass and Memory Bank. Push `v3.0.1` release; CI passes for all platforms.
- 2026-06-07: Refactor membership `checkMembership()` to return local unlimited status without network calls or device-code generation.
- 2025-06-06: Initialize Memory Bank with 7 core files based on existing codebase analysis.

## Active Decisions
- **No remote membership verification**: `checkMembership()` now short-circuits to a fixed `UnlimitedRuntime: true` status. Existing quota/refill/device-code code remains in repo but is effectively unreachable in normal flow.
- **develop branch**: Active feature branch created from `main` for this refactor.

## Blockers
- None.

## Next Steps
1. Monitor for any side effects from bypassing quota enforcement (e.g., unexpected `membership-quota.json` writes).
2. If needed later, clean up unreachable code (device-code generation, HTTP fetch, refill logic, tests).
3. Keep memory bank in sync with future feature additions or refactors.
