---
name: pipeline-guide
description: Use when writing, modifying, or reviewing MaaFramework Pipeline JSON, including node flow, recognition algorithms, actions, retries, waits, anchors, custom components, naming, and reliability.
---

# MaaFramework Pipeline Guide

## Core Model

A node recognizes state, performs an action, then evaluates `next`. Omitted `recognition` defaults to `DirectHit`; omitted `action` defaults to `DoNothing`. V1 string fields and V2 `{type, param}` objects may coexist—match the surrounding file and avoid unrelated conversion.

Use `tools/schema/pipeline.schema.json` as the source of truth and [field-reference.md](field-reference.md) for a compact summary.

## Design Rules

1. Drive the flow from observable screen state: recognize → act → recognize the result.
2. Cover realistic alternate states such as popups, loading, return screens, and already-completed states.
3. Prefer state checks and targeted freeze waits over large fixed delays.
4. Use the project's 1280x720 coordinate/template baseline unless current code establishes another basis.
5. Keep the smallest graph that preserves reliability, reuse, overrides, anchors, and diagnostics.
6. Judge names from actual behavior. Action nodes use verb-object naming; state nodes use object-state naming. See `../pipeline-debug/references/pipeline-node-naming.md`.

## Recognition Selection

- `TemplateMatch`: stable visual asset; crop a focused lossless template and restrict ROI when possible.
- `FeatureMatch`: textured elements with scale/rotation variation; avoid tiny or repetitive templates.
- `ColorMatch`: stable color regions; choose RGB/GRAY/HSV from sampled evidence and set pixel count deliberately.
- `OCR`: textual state; use complete expected text or justified regex, and follow project i18n rules.
- `And`/`Or`: combine reusable node recognitions or inline sub-recognitions.
- `Custom`: only when Pipeline algorithms cannot express the behavior; registration and params must match the agent implementation.

Do not guess thresholds from convention. Compare screenshots, logs, and nearby proven nodes.

## Actions and Control Flow

- `next` is evaluated in order; the first recognized node wins.
- `on_error` handles recognition timeout or action failure.
- `[JumpBack]Name` or NodeAttr `{ "name": "Name", "jump_back": true }` returns to the parent after the child chain.
- `[Anchor]Name` or NodeAttr anchor references resolve a previously assigned anchor.
- `interrupt` is deprecated in the current schema; avoid introducing it.
- Use `max_hit`, timeout, or observable state changes to bound intentional loops.
- There is no `Sleep` action; use node delay/wait fields only when justified.

## Action Safety

- Prefer recognition-result targets or stable anchors over raw coordinates.
- After Click/LongPress/Swipe/InputText/Custom actions, recognize the resulting state before another action.
- Ensure repeated actions cannot hit a different control after the screen changes.
- For freeze waits, choose a meaningful target; `[0,0,0,0]` means the full screen and may be unnecessarily sensitive or expensive.

## Review Checklist

- JSON fields and enums validate against the local schema.
- All node, anchor, target, composite-recognition, and override references resolve.
- Normal, retry, popup, error, and completion paths terminate correctly.
- Custom names/params match agent code.
- Names reflect actual responsibility rather than suffix assumptions.
- The diff does not reformat or redesign unrelated nodes.

