# Project Interface Option Types

Choose the type from the user-facing business choice, then verify it against `tools/schema/interface_import.schema.json` and current MDA examples.

## `switch`

Use for one boolean choice: run/skip, claim/do not claim, enable/disable.

- Exactly two cases.
- Prefer stable names `Yes` and `No`.
- Each case should set the effective Pipeline state explicitly.
- Set `default_case` only when needed to reproduce the intended default.

## `select`

Use for exactly one choice among mutually exclusive routes, modes, targets, or difficulties.

- `default_case` is one case name.
- Each case enables its route and disables incompatible routes unless exclusivity is enforced elsewhere.
- Do not classify siblings as `select` merely because they share a parent.

## `checkbox`

Use for independent items that may be selected together, such as purchase or reward lists.

- Each case normally changes only its own nodes.
- `default_case` is an array of selected case names.
- Do not disable other cases unless the business rules require it.

## Nested Options

Put child option keys in a case's `option[]` only when that case makes the child setting meaningful. Define every child in the outer `option` object and check that nesting cannot expose contradictory controls.

## `input`

Use for user-supplied string, integer, or boolean values.

```json
{
    "type": "input",
    "inputs": [
        {
            "name": "Count",
            "pipeline_type": "int",
            "default": "5"
        }
    ],
    "pipeline_override": {
        "TargetNode": {
            "custom_action_param": {
                "count": "「Count」"
            }
        }
    }
}
```

Use `verify` and `pattern_msg` when invalid input would reach runtime. Confirm the placeholder location is accepted by the current schema/client.

## Decision Check

- One boolean choice: `switch`.
- Exactly one business route: `select`.
- Any subset of independent items: `checkbox`.
- User-provided typed value: `input`.
- Choice only meaningful under another case: nested option.

