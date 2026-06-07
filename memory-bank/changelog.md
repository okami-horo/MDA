# Changelog

All notable changes, decisions, and versions for this project.

## [Unreleased]

### Added
- Initialize Memory Bank with 7 core files capturing project architecture, domain model, and conventions.

### Changed
- **2026-06-07**: Bypass remote membership verification. `checkMembership()` in `memberdata.go` now returns a fixed local unlimited status (`Tier: "Local"`, `UnlimitedRuntime: true`). Device-code generation, HTTP quota fetch, and refill logic are preserved in codebase but no longer executed during normal flow.
- Removed 10-minute daily runtime quota restriction for all users.

## [0.1.0] - Current

### Overview
- MDA (Maa Doro Assistant) initial release on MaaFramework.
- Rewritten from DoroHelper.
- Supports full daily automation suite for NIKKE (Simplified Chinese UI).
