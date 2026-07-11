# 桌面源码一键运行脚本设计

## 目标

在当前用户桌面创建单个 `MDA源码运行.cmd`。用户双击后，脚本从 `E:\Git\MDA` 重新构建 Go Agent，并在构建成功后启动 MXU，使最新 Go 源码和已通过目录联接接入的资源文件生效。

## 执行流程

1. 检查项目目录 `E:\Git\MDA` 是否存在。
2. 检查 PowerShell 7、项目内 `.go\activate.ps1` 和 `tools\build_and_install.py` 是否可用。
3. 检查是否已有 `mxu.exe` 进程；若存在则提示用户关闭后重试，避免占用 Go Agent 构建产物。
4. 通过 PowerShell 7 加载 `.go\activate.ps1`，使用项目内 Go 1.25.6 环境。
5. 执行 `python tools\build_and_install.py`，重新构建 Go Agent 并刷新开发目录联接。
6. 构建成功后，以 `install` 为工作目录启动 `install\mxu.exe`。
7. 启动命令提交成功后关闭命令窗口。

## 错误处理

- 缺少项目目录、PowerShell 7、局部 Go 环境或构建脚本时，显示明确错误并暂停窗口。
- 已有 MXU 进程时不强制结束进程，只提示用户手动关闭，避免权限或未保存状态问题。
- 构建返回非零退出码时不启动 MXU，并保留窗口供用户查看错误。
- 缺少 `install\mxu.exe` 时视为失败，提示重新运行 `tools\setup_workspace.py` 初始化依赖。

## 文件范围

- 桌面文件：`%USERPROFILE%\OneDrive\Desktop\MDA源码运行.cmd`。
- 不修改项目业务代码、配置或运行资源。
- 桌面脚本使用绝对项目路径，适用于当前工作区位置。

## 验证

- 检查桌面脚本存在且内容包含项目路径、构建命令和 MXU 启动命令。
- 使用命令解释器解析并执行脚本，确认 Go Agent 构建成功。
- 确认脚本能够启动位于 `E:\Git\MDA\install\mxu.exe` 的 MXU 进程。
- 确认 Git 工作树除本设计文档外没有其他跟踪文件变化。
