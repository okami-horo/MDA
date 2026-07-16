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
- **Membership bypass is the highest-priority fork constraint**: `checkMembership()` must always return a local unlimited status; upstream membership logic must not be allowed to re-enable remote verification.
- **Win32 Background Capture** as the default recommended controller (`Background` + `SendMessageWithCursorPos`).
- **PascalCase node naming** with strict domain + role suffix conventions (see `docs/pipeline-node-naming.md`).

## Framework vs Project Ownership
- MaaFramework provides the generic Pipeline runtime, recognition algorithms, actions, controllers, Project Interface protocol, and Agent/Custom extension APIs. MaaFramework upstream contains no NIKKE-specific task, screen, navigation, or reward logic.
- MDA owns the NIKKE automation behavior encoded under `assets/resource/pipeline/**/*.json`: node graphs, screen states, OCR text, ROI coordinates, thresholds, retries, popup recovery, and completion conditions. Using Maa's Pipeline DSL does not make these business rules framework-provided.
- MDA also owns the concrete Project Interface task/option definitions and `pipeline_override` mappings under `assets/tasks/**/*.json`, recognition templates under `assets/resource/image`, and project models under `assets/resource/model`.
- The MaaFramework `NeuralNetworkDetect` engine performs inference, while MDA supplies `MapPushing.onnx`, its labels, and the Pipeline behavior that consumes its detections.
- The only current Go custom component directly participating in NIKKE gameplay is `CenterPriorityRecognition`, used by map pushing to choose the detected monster or plate nearest the configured/image center.
- `RuntimeQuotaCheck`, membership/runtime tracking, aspect-ratio checks, HDR checks, process checks, resource-path capture, i18n, and Maa focus output are product policy, environment guardrails, or infrastructure rather than NIKKE gameplay logic. In this fork, membership and runtime enforcement are short-circuited by local unlimited status.
- Most NIKKE business behavior in this repository is inherited from and synchronized with upstream MDA. The defining local fork behavior is preserving the membership bypass, alongside local maintenance, CI, and Memory Bank changes.

## Design Patterns
- **Pipeline Override**: Options use `pipeline_override` to enable/disable specific nodes at runtime.
- **Flow Orchestration**: Complex subtasks are decomposed into `*Flow` nodes that sequence recognition, action, and confirmation steps.
- **Entered Sentinel**: After entering a page, an `*Entered` node acts as a success sentinel; if it hits, the entry subflow ends.
- **Common / Navigation Shared Domains**: Reusable UI interactions live under `Common` (confirm, close, scroll) and `Navigation` (home, main area) to avoid duplication.

## Recognition Architecture
- `assets/interface.json` registers `./resource`; task definitions under `assets/tasks/*.json` select a Pipeline entry node through their `entry` field.
- Recognition and navigation are primarily declarative Pipeline JSON under `assets/resource/pipeline/**/*.json`. A node recognizes the current screen, performs an action, then evaluates `next` candidates in order; the first recognized candidate wins. `on_error` handles recognition timeout or action failure.
- Omitted recognition defaults to `DirectHit`; omitted action defaults to `DoNothing`.
- The project mainly uses `OCR`, `TemplateMatch`, `ColorMatch`, and `And` / `Or`. `NeuralNetworkDetect` is used for map-pushing targets. Template assets live under `assets/resource/image`, and model assets live under `assets/resource/model`.
- Recognition coordinates and templates use the 1280x720 baseline unless the surrounding domain establishes another basis. OCR is designed for the Simplified Chinese game client.
- Prefer observable-state flows: recognize the actionable state, perform the action, then recognize its result. Avoid chaining actions using only fixed delays or unverified coordinates.
- Use Pipeline built-ins whenever possible. Add Go custom recognition only for image processing, candidate selection, external state, or other logic that Pipeline cannot express cleanly.
- The current Go custom recognizer is `CenterPriorityRecognition`. It runs another Pipeline recognition through `ctx.RunRecognition`, selects the candidate nearest the configured/image center, and returns that box. It is registered by `agent/go-service/common/centerpriority/register.go` and aggregated through `agent/go-service/register.go`.
- A new Go custom recognizer must implement `maa.CustomRecognitionRunner`, validate context/parameters, return a meaningful box and detail, register with a name exactly matching Pipeline `custom_recognition`, and include focused tests.
- Validate Pipeline/interface schema changes with `python tools/validate_schema.py --resource-dirs assets/resource --exclude-dirs assets/resource/announcement --interface-files assets/interface.json`. For Go changes, run `go -C agent/go-service test ./...` and `go -C agent/go-service build ./...`. Schema validation does not replace testing against real screenshots and runtime logs.

## Component Relationships
| Component | Consumes | Produces |
|-----------|----------|----------|
| `assets/interface.json` | `tasks/*.json` imports | Runtime PI config |
| `assets/tasks/*.json` | locale keys, pipeline node names | Task + option schema for MXU |
| `assets/resource/pipeline/**/*.json` | template images | Executable node graph for MaaFramework |
| `agent/go-service` | PI env, resource reader | Custom actions/recognizers, membership/quota bypass, center-priority recognizer |
| `assets/locales/interface/*.json` | task/option/controller keys | User-facing UI text |

## Critical Implementation Paths
1. **Task Start**: MXU reads `interface.json` → user selects task + options → MXU generates `pipeline_override` → MaaFramework loads pipeline JSON + override → Tasker executes from `<Domain>Main` entry node.
2. ~~**Quota Enforcement**: Go agent `membership` sink reads device code → queries/refills quota → allows or blocks task start based on remaining daily minutes.~~ **(Disabled 2026-06-07)**: `checkMembership()` now returns a fixed local unlimited status; device-code generation, HTTP quota fetch, and refill logic are preserved but inactive.
3. **Environment Guardrails**: `aspectratio`, `hdrcheck`, `processcheck` sinks run before or alongside tasks to warn about unsupported configurations.

## Data Flow
- User config (task selection + option toggles) flows **down** from MXU to MaaFramework as JSON overrides.
- Run logs (`maafw.log`, `go-service.log`, `mxu-*.log`) flow **up** from the backend to the user for debugging.
- ~~Quota state flows **out** from the Go agent to a remote endpoint and **back** into the run log for user visibility.~~ **(Disabled 2026-06-07)**
