---
name: dmp-analysis
description: Use when an MDA, MaaFramework, or MXU issue/log bundle contains a Windows .dmp file, or when the user asks for crash-dump, minidump, exception-code, crashing-thread, or symbolication analysis.
---

# Windows DMP Analysis

## Goal

Identify the crashing process, exception, module, and most likely ownership from evidence. A dump without matching symbols can support a module-and-offset conclusion, but not a source-line claim.

## Preconditions

- Work only with dumps and logs the user is authorized to provide.
- Prefer `minidump-stackwalk` plus `dump_syms`; check availability before use.
- Do not install global tools or download large symbol packages without user approval.
- Keep the original dump unchanged and perform analysis in `.cache/dmp-analysis/<case>/`.

## Workflow

1. **Identify the session.** Match a PID embedded in the dump filename with `[Px<pid>]` in `maafw.log`, process lifecycle entries in `mxu-tauri.log`, and agent output.
2. **Establish exact versions.** Prefer runtime logs and packaged config over issue text or empty module-version fields. Record MDA, MaaFramework, MXU, architecture, and controller type.
3. **Run an unsymbolicated stackwalk.** Capture the exception code, crashing thread, module list, instruction address, and module offset.
4. **Obtain matching symbols.** Use the exact release tag and architecture. Verify asset names through GitHub before downloading:

```powershell
gh release view "v<VERSION>" --repo MaaXYZ/MaaFramework --json assets
gh release download "v<VERSION>" --repo MaaXYZ/MaaFramework --pattern "MAA-win-x86_64-v<VERSION>.zip" --dir "<work>"

gh release view "v<VERSION>" --repo MistEO/MXU --json assets
gh release download "v<VERSION>" --repo MistEO/MXU --pattern "MXU-win-x86_64-v<VERSION>.zip" --dir "<work>"
```

5. **Convert PDBs.** Run `dump_syms` for relevant PDB files. Use the `MODULE` header values to create Breakpad layout `<module>/<debug-id>/<module>.sym`; do not guess the debug ID.
6. **Run symbolicated stackwalk.** If symbols still do not resolve, report the mismatch and retain module+offset evidence.
7. **Trace source only after version confirmation.** Inspect the matching tag of MaaFramework or MXU and link exact GitHub lines when available.

## Interpretation Rules

- `0xC0000005`: access violation; determine the first meaningful caller before naming a cause.
- `0xC0000409`: Windows fast-fail; it may represent `std::terminate()` or abort rather than a literal buffer overrun.
- `ntdll.dll`, `KERNELBASE.dll`, and `ucrtbase.dll` are usually terminal frames, not ownership evidence.
- GPU, DirectML, ONNX Runtime, OpenCV, OCR, and controller modules require correlation with logs and loaded versions.
- Never infer a project-code bug solely because the project process produced the dump.

## Report

Include dump filename, PID/session, OS/architecture, exception code, crashing thread, symbol status, key module versions, ownership assessment, confidence, user workaround, developer direction, and missing evidence. If a text log and dump disagree, explain the mismatch explicitly.

