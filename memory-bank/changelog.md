# Changelog

All notable changes, decisions, and versions for this project.

## [Unreleased]

## [3.0.3] - 2026-06-16

### Added
- Initialize Memory Bank with 7 core files capturing project architecture, domain model, and conventions.
- Document fork purpose in Memory Bank: this repository removes upstream membership/account-login verification and gives all local users unlimited runtime.

### Changed
- **2026-06-16**: Sync latest `upstream/main` updates (up to `94f2fe9`, v1.6.5) into `develop`. Preserve local membership bypass, Memory Bank, and CI guards.
- **2026-06-13**: Sync latest `upstream/main` updates (up to `ec4ed53`) into `develop`: ArkRanger mini-game option, activity-option switches, preset cleanup, and project refactor. Preserve local membership bypass and Memory Bank. Push `v3.0.2` release; CI passes for all platforms.
- **2026-06-12**: Merge `upstream/main` v1.6.2 into `develop`: new ARK RANGER event, BlaBla/Rhythm red-dot clearing, cube/recycle-room nurturing, auto battle character selection, and many bug fixes. Preserve local membership bypass and Memory Bank. Push `v3.0.1` release; CI passes for all platforms.
- **2026-06-12**: Refine `productContext.md` and `projectBrief.md` to remove leftover membership/quota language and explicitly describe the fork.
- **2026-06-07**: Bypass remote membership verification. `checkMembership()` in `memberdata.go` now returns a fixed local unlimited status (`Tier: "Local"`, `UnlimitedRuntime: true`). Device-code generation, HTTP quota fetch, and refill logic are preserved in codebase but no longer executed during normal flow.
- Removed 10-minute daily runtime quota restriction for all users.

### Fixed
- 适配部分页面活动地区区域变化弹窗。
- 调整活动地区识别文本。
- 优化小游戏点击返回流程。
- 调整点击徽章贴纸的偏移量。
- 调整进入战斗识别文本。
- 为竞技场领取累积奖励添加点击次数上限。
- 修正自由状态确认流程。
- 调整付费商店领取流程。
- 更新日常预设文案并精简快速/自用预设选项。

## [3.0.2] - 2026-06-13

### Added
- ArkRanger mini-game task option.
- Activity content options converted to on/off switches (`LargeEventLoginStamp`, `LargeEventChallenge`, `LargeEventStory`, `LargeEventMission` and SmallEvent equivalents).

### Changed
- Presets (`DailyFull`, `SelfUse`) cleaned up to remove duplicate task entries.
- Project architecture refactored; `StarAnis` pipeline moved to `Event/Special/` alongside new `ArkRanger.json`.
- Synchro device enhancement recognition area adjusted.
- Large event story page navigation logic improved.

## [3.0.1] - 2026-06-12

### Added
- New large event **ARK RANGER** support.
- Auto-select battle character.
- Cube enhancement and recycle-room upgrade in Account Nurturing.
- BlaBla and Rhythm Game red-dot clearing.
- Renewal reminder logic (guarded by `UnlimitedRuntime` flag; inactive in this fork).
- `centerpriority` custom recognizer.

### Changed
- Improved arena, advise, red-dot clearing, map-pushing, email, and friendship-point flows.
- Portrait aspect-ratio detection fixed.
- Added `3rdparty` to `.gitignore`; removed `scripts/setup-local-env.ps1`.

### Fixed
- Multiple dead-loop and stuck scenarios in red-dot clearing, arena reward collection, and event flows.

## [0.1.0] - Current

### Overview
- MDA (Maa Doro Assistant) initial release on MaaFramework.
- Rewritten from DoroHelper.
- Supports full daily automation suite for NIKKE (Simplified Chinese UI).
