# Pipeline Node Naming

Names are diagnostic clues, not authoritative behavior. Always inspect recognition, action, references, and runtime role before renaming a node.

## Shape

Use PascalCase with a stable business domain:

```text
<Domain><SemanticPart><Role>
```

Examples: `ShopPurchaseGem`, `BattleStartButtonBlocked`, `CommonConfirmReward`, `DailyRewardsClaimRewardFlow`.

## Role Rules

- **Actions use verb-object order:** `EnterPage`, `ClickButton`, `SelectTarget`, `ClaimReward`, `PurchaseItem`, `ConfirmAction`, `ClosePage`.
- **Pure states use object-state order:** `ButtonVisible`, `TargetAvailable`, `RewardClaimed`, `OptionSelected`, `TaskCompleted`, `AttemptsExhausted`.
- **Orchestration:** `<Domain>Main` for an entry and `<Domain><Goal>Flow` for a node that primarily sequences branches.
- **Entry success sentinel:** `<Domain><Page>Entered` when the node proves a preceding entry action succeeded.
- **Page state:** `<Domain>On<Page>Page`; UI objects generally use `Visible` or a more precise business state.
- Use `Detected` only when a business-state suffix is inaccurate, typically for algorithmic or abnormal conditions.

Do not force a name to match a suffix if the implementation has a different responsibility. A `Visible` node that clicks is an action node; a `Click` node with `DoNothing` is not a click action.

## Avoid

- Temporary names such as `Node1`, `Check2`, `_Start`, or numeric prefixes.
- snake_case/camelCase mixtures.
- Globally vague names such as `Confirm`, `Click`, or `Check`.
- Legacy `FlagInX` names for new page-state nodes.
- One-use wrapper nodes that add no reusable recognition, control flow, override target, anchor, or diagnostic value.

## Rename Checklist

Update all `next`, `on_error`, deprecated `interrupt`, string ROI/target, `And`/`Or`, anchor, and `pipeline_override` references. Do not alter recognition/action parameters during a naming-only change.

