---
name: mda-issue-log-analysis
description: Use when analyzing an MDA GitHub issue, exported log bundle, local runtime logs, recognition failure, stuck task, controller difference, Pipeline failure, Go Agent failure, MXU failure, or attached Windows dump.
---

# MDA Issue and Log Analysis

## Scope

The canonical issue repository is `1204244136/MDA`. Accept an issue URL, `#<number>`, a log directory, an archive, or individual logs. Treat maintainer comments as hypotheses until logs or code confirm them.

**REQUIRED SUB-SKILL:** Use `dmp-analysis` whenever a `.dmp` file exists.

## Evidence Collection

For GitHub issues, use `gh`:

```powershell
gh issue view <number> --repo 1204244136/MDA --comments
```

Extract archives into `.cache/issue-logs/<case>/`, list their contents, and preserve the original archive. Look for:

- `maafw.log` and `maafw.bak.*.log`
- `go-service.log`
- `mxu-tauri.log`
- `mxu-web-*.log`
- `mxu-agent*.log`
- `config/`, `on_error/`, and `.dmp`

If several bundles exist, start with the latest confirmed reproduction, then compare older successful or contrasting runs.

## Analysis Order

1. Normalize version, controller, task entry, user options, expected behavior, and observed behavior.
2. Identify the reproduction time and `task_id`; do not mix historical runs from the same bundle.
3. Build a timeline across layers:
   - `mxu-web-*`: submitted tasks, options, and UI state.
   - `mxu-tauri.log`: instance, controller, resource, task, and agent lifecycle.
   - `maafw*.log`: node recognition/action, timeout, callback, and task result.
   - `go-service.log`: custom logic and environment checks.
   - `mxu-agent*.log`: captured child-process output.
   - `on_error/`: actual screen at failure.
4. Map evidence back to `assets/tasks/`, `assets/interface.json`, `assets/resource/pipeline/`, `agent/go-service/`, and `tools/schema/`.
5. Check upstream MaaFramework/MXU code only when evidence points there or local evidence is insufficient.

## Evidence Rules

- A final `Tasker.Task.Succeeded` means that log did not reproduce a claimed task failure; report fragile code separately as risk.
- Repeated recognition failure suggests a wrong state branch, template/OCR mismatch, missing intermediate state, popup, controller difference, HDR, or resolution issue; identify which evidence supports the choice.
- Environment warnings are not automatically the root cause.
- Compare logs against the user's version tag/commit, not only current `HEAD`.
- Prefer screenshots over recollection when they conflict.
- Quote only the lines needed to support the conclusion.
- Use localized labels from `assets/locales/interface/zh_cn.json` when describing user-visible tasks/options.

## Output

Report the reproduction context, concise timeline, key log/screenshot/code evidence, direct cause, confidence, immediate user workaround, code/config fix direction, and missing evidence. Include a dedicated DMP section when applicable. Use GitHub blob links pinned to the analyzed commit for issue-facing reports.

