---
name: pipeline-debug
description: Use when a MaaFramework Pipeline JSON behaves incorrectly, times out, loops, misclicks, has missing references, fails schema validation, has unreliable ROI/thresholds, or needs correctness and maintainability review.
license: MIT
compatibility: Designed for Codex
---

# Debug MaaFramework Pipelines

## Authority

Read `tools/schema/pipeline.schema.json` first. The current schema permits omitted `recognition` and `action`, which default to `DirectHit` and `DoNothing`; an empty orchestration node is not inherently invalid. V1 string fields and V2 `{type, param}` fields may coexist.

## Workflow

1. Parse the target JSON/JSONC and identify the actual task entry from `assets/tasks/` or caller context.
2. Build a graph from `next` and `on_error`. Include references from `And.all_of`, `Or.any_of`, string ROI/target values, anchors, and Project Interface `pipeline_override` when relevant.
3. Validate every node against the local schema: field names/types, recognition/action enums, required algorithm parameters, ranges, and custom registration names.
4. Trace the reported runtime path using logs/screenshots. Separate confirmed failures from static risks.
5. Inspect each node's actual recognition, action, and control-flow role before judging its name. Use [pipeline-node-naming.md](references/pipeline-node-naming.md) as guidance, not as proof.
6. Rank findings by correctness, reliability, performance, then maintainability.

## Structural Checks

- Every referenced node or anchor resolves.
- Entry reachability is evaluated from known task entries; an unreferenced entry node is not an orphan.
- A cycle is only a defect when it lacks an effective exit, timeout, `max_hit`, state change, or intentional retry behavior.
- A node without `next` is valid when successful execution should end that chain.
- `interrupt` is deprecated by the current schema; recommend `[JumpBack]`/NodeAttr migration when touching related flow.
- Do not invent a `sub` or `Sleep` action; neither is part of the current node/action schema.
- Click/Swipe targets and string ROIs must refer to a previously available recognition result or anchor.

## Reliability Checks

- Each destructive or state-changing action is followed by recognition of the resulting state.
- Repeated clicks cannot accidentally act on a changed screen.
- Popups, loading states, network variance, and return-to-home behavior are covered where the task can encounter them.
- `pre_delay`/`post_delay` are not used as substitutes for a missing state check.
- Freeze waits use a meaningful target and timeout.
- ROI, template, OCR, and ColorMatch parameters are judged from screenshots/logs and nearby proven nodes; do not label a threshold wrong without evidence.
- Custom names and params match `agent/go-service` registration and parsing.

## Output

Lead with the direct cause and evidence. For each finding include severity, node, observed behavior, why it fails, and the smallest correction. Mark uncertain items as requiring runtime evidence. Provide only the relevant corrected JSON unless the user asks for the complete file.

