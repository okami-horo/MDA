---
name: mda-project-guide
description: Use when changing or reviewing MDA-specific Pipeline JSON, Project Interface tasks/options, interface or Go-service locales, Go Agent components, task naming, or repository conventions.
---

# MDA Project Guide

## Authority

Read the repository `AGENTS.md` first. This skill records MDA-specific structure and judgment that should not be duplicated in generic MaaFramework skills.

## Stable Structure

- `assets/interface.json`: Project Interface root config and imports.
- `assets/tasks/*.json`: task and option definitions.
- `assets/tasks/preset/*.json`: preset snapshots when present.
- `assets/resource/pipeline/**/*.json`: Pipeline nodes.
- `assets/locales/interface/{zh_cn,en_us}.json`: interface strings.
- `assets/locales/go-service/{zh_cn,en_us}.json`: Go-service strings.
- `agent/go-service/`: Go Agent module.
- `tools/schema/`: local authoritative schemas.

Do not hardcode an absolute checkout path or a static task/domain inventory. Discover current files with `rg --files` before editing.

## Project Interface Conventions

- Imported task paths are relative to `assets/interface.json`, for example `tasks/Shop.json`.
- Maintain only locale files that currently exist; MDA presently uses `zh_cn` and `en_us` for interface and Go-service strings.
- User-visible text should use `$` locale keys.
- Choose option type from business semantics: one toggle=`switch`, mutually exclusive routes=`select`, independent items=`checkbox`, typed user value=`input`.
- Verify every task option reference, nested option, `pipeline_override` node, group, controller, and resource against current files/schema.

## Pipeline Conventions

- Use existing top-level domains and directory placement where possible.
- Review each node's actual recognition, action, and control-flow responsibility; a suffix such as `Visible`, `Click`, `Flow`, or `Entered` is a clue, not proof.
- Action nodes use verb-object naming; pure state nodes use object-state naming.
- An `Entered` node is valuable when it is the success sentinel for an entry action, even if referenced once.
- Avoid one-use wrapper nodes that add no reusable recognition, control-flow, override, or diagnostic value.
- Coordinates and templates use the project's 1280x720 baseline unless the surrounding code establishes another basis.

## Go Service Conventions

- The Go module is `agent/go-service`.
- `registerAll()` in `agent/go-service/register.go` aggregates package registration.
- Custom registration names must exactly match Pipeline custom names.
- Follow existing zerolog, package, interface-assertion, and locale patterns.
- Run Go checks from the repository root with `go -C agent/go-service test ./...` and `go -C agent/go-service build ./...` when Go is available.

## Final Checks

- Imported task file and locale keys resolve.
- Pipeline references and overrides resolve.
- Node names match actual behavior, not only naming heuristics.
- New Go components are registered and tested.
- No unrelated files or locale ordering are changed.

