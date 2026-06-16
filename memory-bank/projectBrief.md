# Project Brief

## Overview
MDA (Maa Doro Assistant) is a game automation assistant for the mobile game **NIKKE / 勝利女神：妮姬** (Goddess of Victory: Nikke), built on top of [MaaFramework](https://github.com/MaaXYZ/MaaFramework). It was rewritten from the earlier project [DoroHelper](https://github.com/1204244136/DoroHelper).

This repository is a fork of [1204244136/MDA](https://github.com/1204244136/MDA). **The primary purpose of this fork is to disable the upstream remote membership / account-login verification and ensure all local users have unlimited runtime.** This goal takes precedence over all other maintenance work, including upstream synchronization. The project targets **Windows only**.

## Goals
- Automate daily and periodic in-game tasks for NIKKE players.
- Provide a stable, user-friendly automation experience via MXU frontend + MaaFramework backend.
- Support both Win32 window capture and ADB controllers.
- Continuously sync upstream improvements while preserving local fork modifications (membership bypass, Memory Bank, CI fixes).
- **Never re-enable remote membership verification during any upstream merge or refactor.**

## Requirements
- Windows OS (PowerShell 7).
- Game client running in **Simplified Chinese** interface (script recognition is CN-only).
- NIKKE game window (`UnityWndClass`) or ADB-connected device.
- Go 1.25.6+ for building the Go agent.

## Constraints
- **Windows-only** — no Linux/macOS support.
- **PowerShell 7** for all terminal / build / dev commands.
- Game UI language locked to Simplified Chinese for recognition accuracy.
- ~~Daily runtime quota enforced by Go agent (free tier: 10 min/day, resets at 04:00).~~ **(Removed 2026-06-07)**: Remote membership verification bypassed; all local users default to unlimited runtime.
- Interface localization limited to `zh_cn` and `en_us`.

## Success Criteria
- **Remote membership verification remains disabled in every build and every branch; `checkMembership()` must return local unlimited status.**
- All tasks complete successfully on standard NIKKE UI flows.
- Pipeline nodes follow the project's PascalCase naming conventions and domain boundaries.
- Go agent compiles and registers all custom sinks correctly.
- locale keys stay synchronized across `zh_cn` and `en_us`.
- Every upstream sync ends with a diff review confirming `agent/go-service/taskersink/membership/memberdata.go` still bypasses verification.
