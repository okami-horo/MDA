---
name: generate-pi-task
description: Use when creating or updating MaaFramework Project Interface task JSON under assets/tasks, exposing Pipeline behavior as switch/select/checkbox/input options, adding pipeline_override entries, imports, or interface locale keys.
license: MIT
compatibility: Designed for Codex
---

# Generate Project Interface Tasks

## Principle

Expose meaningful user choices, not every Pipeline implementation detail. The local schemas and current sibling task files are authoritative.

## Workflow

1. Read `tools/schema/interface_import.schema.json`, `tools/schema/interface.schema.json`, and `tools/schema/pipeline.schema.json`.
2. Read `assets/interface.json` and its imported task files. Collect task names, option keys, groups, controller/resource filters, and locale files.
3. Determine the target task and Pipeline entry. For a new task file, add its path to `assets/interface.json` using `tasks/<Name>.json`.
4. Inspect all Pipeline files involved in the task. Record node names, `enabled`, references, recognition/action behavior, and business relationships.
5. Model options using [option-types.md](references/option-types.md). Do not infer mutual exclusion solely from sibling position or `enabled` fields.
6. Add only the required task/option JSON and locale keys. Follow formatting and ordering of neighboring files.
7. Validate references and defaults against the actual Pipeline state.

## Required Rules

- `entry` exactly matches a Pipeline node.
- Every `task[].option[]` and nested `case.option[]` key exists in the file's `option` object.
- Every `pipeline_override` target exists in loaded Pipeline resources.
- `select` cases disable incompatible routes when the Pipeline does not already guarantee exclusivity.
- `checkbox` cases remain independent and do not disable unrelated siblings.
- A `switch` has exactly two Yes/No-compatible cases as required by the schema.
- `input` values use only schema-supported `pipeline_type` values and `「Name」` placeholders.
- Every `$...` value resolves in all existing interface locale files.
- Defaults reproduce the Pipeline's effective default behavior.
- Do not create new locale languages unless explicitly requested.

## Validation Checklist

- JSON parses successfully.
- Task file validates against `interface_import.schema.json`.
- New import path resolves.
- All task, nested option, locale, group, controller, resource, and Pipeline references resolve.
- UI defaults and Pipeline defaults agree.
- The diff contains no unrelated reordering or formatting.

