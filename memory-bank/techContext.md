# Tech Context

## Technology Stack
| Layer | Tech |
|-------|------|
| Core Framework | MaaFramework (C++) |
| Frontend | MXU (Tauri-based GUI) |
| Agent Language | Go 1.25.6 |
| Go Framework | maa-framework-go v4.0.0-beta.14 |
| Logging | zerolog |
| OS APIs | golang.org/x/sys (Windows) |
| Controllers | Win32 (Background / PrintWindow / ScreenDC), ADB |
| Config Format | Project Interface JSON v2 |
| Pipeline Format | MaaFramework Pipeline JSON |

## Development Setup
- **OS**: Windows 10/11
- **Shell**: PowerShell 7
- **Go module location**: `agent\go-service\`
- **Build agent**: `go build` from `agent/go-service` (or repo root per conventions).
- **Test agent**: `go test ./...` from repo root.
- **Run MXU + MDA**: Load MDA folder as a MaaFramework resource in MXU.

## Dependencies
Key Go deps (from `agent/go-service/go.mod`):
- `github.com/MaaXYZ/maa-framework-go/v4 v4.0.0-beta.14`
- `github.com/rs/zerolog v1.34.0`
- `golang.org/x/sys v0.22.0`

Upstream references:
- MaaFramework: https://github.com/MaaXYZ/MaaFramework
- MXU: https://github.com/MistEO/MXU
- maa-framework-go: https://github.com/MaaXYZ/maa-framework-go

## Technical Constraints
- All terminal commands must use **PowerShell 7** syntax.
- Windows local paths in terminal use backslash `\`; URLs/imports use forward-slash `/`.
- Avoid Bash heredoc, `grep`, `find`, `sed`, `awk` in terminal commands.
- Game UI must be Simplified Chinese for recognition templates/OCR to match.
- locale files only maintain `zh_cn` and `en_us`.
- Pipeline node names must be globally unique PascalCase; renaming requires checking all references (`next`, `on_error`, `target`, `anchor`, `pipeline_override`, `And`/`Or` conditions).

## Tool Usage Patterns
- File search: use `Get-ChildItem -Recurse` (PowerShell) or Claude Code tools.
- Text search: use `Select-String` (PowerShell) or Claude Code tools.
- Go commands: run from repo root or `agent/go-service` as documented.
- Commit style: Chinese messages following Conventional Commits.
- Do **not** auto-push after commit; let the user decide.
