---
name: go-service-guide
description: Use when writing, modifying, or reviewing MDA code under agent/go-service, including MaaFramework Go custom actions, custom recognitions, Tasker/Context event sinks, registration, structured logging, parameters, and tests.
---

# MDA Go Service Guide

## Design Boundary

Keep navigation and business sequencing in Pipeline JSON. Use Go for logic that Pipeline cannot express cleanly: image algorithms, system checks, persistent state, external data, or event-driven behavior.

## Repository Pattern

- `agent/go-service/register.go` owns `registerAll()`.
- A component package exposes `Register()` and performs its own registration.
- Registration strings exactly match Pipeline `custom_action` or `custom_recognition` names.
- Put reusable helpers in the existing `pkg/` structure; avoid a new abstraction for one component.

## Required Signatures

```go
var _ maa.CustomActionRunner = &MyAction{}
func (a *MyAction) Run(ctx *maa.Context, arg *maa.CustomActionArg) bool

var _ maa.CustomRecognitionRunner = &MyRecognition{}
func (r *MyRecognition) Run(ctx *maa.Context, arg *maa.CustomRecognitionArg) (*maa.CustomRecognitionResult, bool)

var _ maa.TaskerEventSink = &MySink{}
func (s *MySink) OnTaskerTask(tasker *maa.Tasker, event maa.EventStatus, detail maa.TaskerTaskDetail)
```

Implement every method required by an event-sink interface. Keep compile-time interface assertions beside the implementation.

## Registration

Follow the current package pattern and handle registration errors when the API returns one:

```go
func Register() {
    if err := maa.AgentServerRegisterCustomRecognition("MyRecognition", &MyRecognition{}); err != nil {
        log.Error().Err(err).Msg("failed to register MyRecognition")
    }
}
```

Then call the package's `Register()` from `registerAll()`.

## Parameters and Results

- Check `ctx`, `arg`, and image inputs before dereferencing when nil is possible.
- Parse `arg.CustomActionParam` or `arg.CustomRecognitionParam` with `encoding/json` into a local struct.
- Log parse failures with `.Err(err)` and return failure.
- A successful custom recognition returns a meaningful `maa.Rect` and valid JSON detail when downstream code consumes it.
- Do not silently swallow I/O, system, image, or serialization errors.

## Logging and Style

Use zerolog fields for context and keep `Msg` stable:

```go
log.Error().
    Err(err).
    Str("component", "MyRecognition").
    Str("task", arg.CurrentTaskName).
    Msg("failed to parse custom recognition param")
```

Match existing package layout, naming, comments, and error behavior. Avoid `panic`, `log.Printf`, unexplained sleeps, and moving whole workflows from Pipeline into Go.

## Verification

From the repository root, when Go is available:

```powershell
go -C agent/go-service test ./...
go -C agent/go-service build ./...
```

Also verify registration names against Pipeline JSON and update both `assets/locales/go-service/zh_cn.json` and `en_us.json` for new user-visible messages.

