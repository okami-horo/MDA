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
- **Project-local Go**: Go 1.25.6 is installed under `.go\sdk\`; run `. .\.go\activate.ps1` before Go commands. `.go\`, `.cache\`, and `install\` are ignored local runtime directories.
- **Initialize local runtime**: Run `python tools\setup_workspace.py` from the repository root. It builds the Go Agent, creates development directory junctions from `install\` to source assets, and downloads MaaFramework and MXU releases.
- **Rebuild agent**: Run `python tools\build_and_install.py` after Go source changes. Pipeline JSON, task, image, and locale changes are consumed through development junctions after MXU restarts.
- **Build verification**: Run `go -C agent/go-service build ./...` from the repository root.
- **Test agent**: Run `go -C agent/go-service test ./...` from the repository root. The current suite has one known stale test: `TestCheckMembershipUnavailableFallsBackToFreeStatus` expects the upstream free-status fallback, while this fork intentionally returns local unlimited status.
- **Run MXU + MDA**: Start `install\mxu.exe`. The desktop script `%USERPROFILE%\OneDrive\Desktop\MDA源码运行.cmd` checks the environment, rebuilds the Go Agent, and starts MXU in one action.
- **Update runtime dependencies**: Run `python tools\setup_workspace.py --update`.
- **Current local runtime versions (2026-07-11)**: MaaFramework v5.11.1 and MXU v2.3.0.
- **Current submodule workaround**: Full `MaaCommonAssets` cloning was interrupted by network resets, so the exact required `OCR/ppocr_v5/zh_cn` blobs from gitlink commit `9adc92ed264318c4d13dcf6df4565c746169a20e` were downloaded and verified locally. Run `git submodule update --init --recursive` when the network is stable to restore full submodule metadata.

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
