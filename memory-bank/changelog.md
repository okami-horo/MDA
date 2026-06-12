# Changelog

All notable changes, decisions, and versions for this project.

## [Unreleased]

### Added
- Initialize Memory Bank with 7 core files capturing project architecture, domain model, and conventions.
- Document fork purpose in Memory Bank: this repository removes upstream membership/account-login verification and gives all local users unlimited runtime.

### Changed
- **2026-06-12**: Refine `productContext.md` and `projectBrief.md` to remove leftover membership/quota language and explicitly describe the fork.

### Changed
- **2026-06-07**: Bypass remote membership verification. `checkMembership()` in `memberdata.go` now returns a fixed local unlimited status (`Tier: "Local"`, `UnlimitedRuntime: true`). Device-code generation, HTTP quota fetch, and refill logic are preserved in codebase but no longer executed during normal flow.
- Removed 10-minute daily runtime quota restriction for all users.

### Notes
- `upstream/main` is at v1.6.2, 46 commits ahead of local `develop`; no merge performed yet.

## [0.1.0] - Current

### Overview
- MDA (Maa Doro Assistant) initial release on MaaFramework.
- Rewritten from DoroHelper.
- Supports full daily automation suite for NIKKE (Simplified Chinese UI).
