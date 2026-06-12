# System Patterns

## Architecture Overview
MDA follows the **MaaFramework + Project Interface + MXU** stack:

```
┌─────────────────────────────────────┐
│  MXU Frontend (GUI)                 │
│  - Loads interface.json             │
│  - Renders tasks, options, locales  │
│  - Submits pipeline_override config │
└─────────────┬───────────────────────┘
              │
┌─────────────▼───────────────────────┐
│  MaaFramework Core (C++)            │
│  - Tasker / Pipeline engine         │
│  - Recognition (Template/OCR/Color) │
│  - Controller (Win32 / ADB)         │
└─────────────┬───────────────────────┘
              │ child_exec
┌─────────────▼───────────────────────┐
│  Go Agent (agent/go-service)        │
│  - Custom recognizers / actions     │
│  - Environment checks (HDR, ratio)  │
│  - Membership / quota logic         │
│    (bypassed in this fork)          │
└─────────────────────────────────────┘
```

## Key Technical Decisions
- **Project Interface v2** for declarative task/option modeling.
- **Go Agent** for logic that is awkward to express in pure Pipeline JSON (membership bypass, Windows API checks).
- **Win32 Background Capture** as the default recommended controller (`Background` + `SendMessageWithCursorPos`).
- **PascalCase node naming** with strict domain + role suffix conventions (see `docs/pipeline-node-naming.md`).

## Design Patterns
- **Pipeline Override**: Options use `pipeline_override` to enable/disable specific nodes at runtime.
- **Flow Orchestration**: Complex subtasks are decomposed into `*Flow` nodes that sequence recognition, action, and confirmation steps.
- **Entered Sentinel**: After entering a page, an `*Entered` node acts as a success sentinel; if it hits, the entry subflow ends.
- **Common / Navigation Shared Domains**: Reusable UI interactions live under `Common` (confirm, close, scroll) and `Navigation` (home, main area) to avoid duplication.

## Component Relationships
| Component | Consumes | Produces |
|-----------|----------|----------|
| `assets/interface.json` | `tasks/*.json` imports | Runtime PI config |
| `assets/tasks/*.json` | locale keys, pipeline node names | Task + option schema for MXU |
| `assets/resource/pipeline/**/*.json` | template images | Executable node graph for MaaFramework |
| `agent/go-service` | PI env, resource reader | Custom actions/recognizers, membership/quota bypass |
| `assets/locales/interface/*.json` | task/option/controller keys | User-facing UI text |

## Critical Implementation Paths
1. **Task Start**: MXU reads `interface.json` → user selects task + options → MXU generates `pipeline_override` → MaaFramework loads pipeline JSON + override → Tasker executes from `<Domain>Main` entry node.
2. ~~**Quota Enforcement**: Go agent `membership` sink reads device code → queries/refills quota → allows or blocks task start based on remaining daily minutes.~~ **(Disabled 2026-06-07)**: `checkMembership()` now returns a fixed local unlimited status; device-code generation, HTTP quota fetch, and refill logic are preserved but inactive.
3. **Environment Guardrails**: `aspectratio`, `hdrcheck`, `processcheck` sinks run before or alongside tasks to warn about unsupported configurations.

## Data Flow
- User config (task selection + option toggles) flows **down** from MXU to MaaFramework as JSON overrides.
- Run logs (`maafw.log`, `go-service.log`, `mxu-*.log`) flow **up** from the backend to the user for debugging.
- ~~Quota state flows **out** from the Go agent to a remote endpoint and **back** into the run log for user visibility.~~ **(Disabled 2026-06-07)**
