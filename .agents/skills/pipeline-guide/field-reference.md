# Pipeline Field Reference

This is a compact guide for the schema currently stored at `tools/schema/pipeline.schema.json`. Read the schema for complete types, defaults, version notes, and new fields.

## Node Fields

| Field | Default | Purpose |
| --- | --- | --- |
| `recognition` | `DirectHit` | Recognition type; string (V1) or `{type,param}` (V2). |
| `action` | `DoNothing` | Action type; string (V1) or `{type,param}` (V2). |
| `next` | empty | Ordered candidate nodes after a successful action. |
| `on_error` | empty | Nodes evaluated after recognition timeout or action failure. |
| `rate_limit` | `1000` ms | Minimum recognition-loop interval. |
| `timeout` | `20000` ms | Recognition timeout; `-1` waits indefinitely. |
| `enabled` | `true` | Disabled nodes are skipped. |
| `max_hit` | unlimited | Maximum successful hits for the node. |
| `pre_delay` / `post_delay` | `200` ms | Fixed delays before/after action. |
| `pre_wait_freezes` / `post_wait_freezes` | `0` | Wait for visual stability before/after action. |
| `repeat` | `1` | Action execution count. |
| `repeat_delay` / `repeat_wait_freezes` | `0` | Delay/stability wait between repeated actions. |
| `inverse` | `false` | Invert recognition success. |
| `anchor` | empty | Assign one or more dynamic anchors. |
| `focus` | `null` | Optional notification payload. |
| `attach` | `{}` | Metadata merged with defaults. |
| `interrupt` | deprecated | Use JumpBack node attributes instead. |

Lifecycle order:

```text
pre_wait_freezes -> pre_delay -> action ->
[repeat_wait_freezes -> repeat_delay -> action] x (repeat - 1) ->
post_wait_freezes -> post_delay -> evaluate next
```

## Recognition Types

| Type | Important parameters |
| --- | --- |
| `DirectHit` | No required algorithm parameter. |
| `TemplateMatch` | `template` required; `roi`, `threshold` (default `0.7`), `method`, `order_by`, `index`, `green_mask`. |
| `FeatureMatch` | `template` required; `count` (`4`), `detector` (`SIFT`), `ratio` (`0.6`), ROI/result selection. |
| `ColorMatch` | `lower` and `upper` required; `method` (`4` RGB; common `6` GRAY, `40` HSV), `count`, `connected`. |
| `OCR` | `expected` optional and regex-capable; `threshold` (`0.3`), `replace`, `only_rec`, `model`, `color_filter`. |
| `NeuralNetworkClassify` | Model, labels, expected classes, ROI/result selection. |
| `NeuralNetworkDetect` | Model, labels, expected classes, thresholds, ROI/result selection. |
| `And` | `all_of` required; node names or inline recognitions, optional `box_index`. |
| `Or` | `any_of` required; node names or inline recognitions. |
| `Custom` | `custom_recognition` required; arbitrary `custom_recognition_param`, optional ROI. |

Recognition ROI may be `[x,y,w,h]`, a previous node name, or an anchor reference where allowed. `[0,0,0,0]` represents the full screen.

## Action Types

Current schema actions include `DoNothing`, `Click`, `LongPress`, `Swipe`, `MultiSwipe`, touch actions, `Scroll`, key actions, `InputText`, app start/stop, `StopTask`, `Command`, `Shell`, `Screencap`, and `Custom`.

- Click/LongPress targets: `true`, node/anchor string, point, or rectangle. `target_offset` is `[x,y,w,h]`.
- Swipe supports target-based begin/end, offsets, duration, end hold, contact, and pressure.
- Custom action requires `custom_action`; `custom_action_param` is arbitrary JSON.

## Node Attributes

References in `next` and `on_error` may use:

```json
[
    {"name": "CommonConfirm", "jump_back": true},
    {"name": "CurrentPage", "anchor": true}
]
```

String shorthand uses `[JumpBack]CommonConfirm` and `[Anchor]CurrentPage`.
