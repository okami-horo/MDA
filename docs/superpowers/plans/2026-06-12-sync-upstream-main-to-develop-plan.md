# 同步 upstream/main (v1.6.2) 到 develop 分支实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `upstream/main`（commit `4ba88f2`，tag `v1.6.2`）的更新完整合并到 `develop` 分支，保留本地会员绕过、Memory Bank 和 CI 修复，解决合并冲突并验证构建/测试通过。

**Architecture:** 使用 `git merge upstream/main` 在 `develop` 分支生成合并提交；冲突文件按既定策略手动合并，以 upstream 新增内容为主，仅保留本地必须保留的关键改动；合并后运行 Go 编译与单元测试验证。

**Tech Stack:** Git、Go、MaaFramework Go binding、PowerShell 7

---

## File Structure

本次同步会创建、修改和删除以下文件：

| 文件 | 操作 | 说明 |
|------|------|------|
| `.gitignore` | 修改 | 合并上游新增 `3rdparty` 忽略项与换行修正，保留本地规则 |
| `.vscode/settings.json` | 修改 | 接受上游新增的 JSONC 格式化配置 |
| `.github/workflows/install.yml` | 修改 | 接受上游删除的 `permissions` 条件块，保留本地仓库所有者的 CI 修复逻辑 |
| `agent/go-service/common/centerpriority/recognition.go` | 创建 | 上游新增的通用识别器 |
| `agent/go-service/common/centerpriority/recognition_test.go` | 创建 | 对应单元测试 |
| `agent/go-service/common/centerpriority/register.go` | 创建 | 识别器注册 |
| `agent/go-service/register.go` | 修改 | 注册新增的 `centerpriority` |
| `agent/go-service/taskersink/aspectratio/checker.go` | 修改 | 上游修正竖屏分辨率检测 |
| `agent/go-service/taskersink/aspectratio/checker_test.go` | 创建 | 新增单元测试 |
| `agent/go-service/taskersink/membership/action.go` | 修改 | 增加 `maybePrintRenewalReminder` 调用 |
| `agent/go-service/taskersink/membership/memberdata.go` | 修改 | 合并上游新增字段，保留 `checkMembership()` 本地绕过 |
| `agent/go-service/taskersink/membership/memberdata_test.go` | 修改 | 上游补充的测试用例 |
| `agent/go-service/taskersink/membership/renewal_reminder.go` | 创建 | 上游新增续费提醒逻辑 |
| `agent/go-service/taskersink/membership/renewal_reminder_test.go` | 创建 | 续费提醒单元测试 |
| `assets/locales/go-service/*.json` | 修改 | 新增 `renewal_reminder` 等本地化键 |
| `assets/locales/interface/*.json` | 修改 | 界面文本更新 |
| `assets/resource/image/**` | 创建/修改 | 新增 ARK RANGER、BlaBla、音游、战斗角色选择等模板 |
| `assets/resource/pipeline/**` | 创建/修改 | 新增/修改各流程配置 |
| `assets/tasks/*.json` | 修改 | 任务入口配置更新 |
| `memory-bank/*.md` | 保留 | 本地新增文件，不跟随上游删除 |
| `scripts/setup-local-env.ps1` | 删除 | 跟随上游删除 |

---

## Task 1: 前置检查

**Files:** 无

- [ ] **Step 1: 确认当前分支和工作区状态**

运行：

```powershell
git branch --show-current
git status --short
```

预期：`develop` 分支，工作区干净（仅有预期的未跟踪文件）。

- [ ] **Step 2: 确认 upstream 最新状态**

运行：

```powershell
git fetch upstream
git log --oneline -1 upstream/main
```

预期：`upstream/main` 指向 `4ba88f2 fix: 调整竞技场识图文本` 或更新。

- [ ] **Step 3: 备份当前 develop 分支**

运行：

```powershell
git branch backup/develop-before-upstream-sync
```

预期：创建本地备份分支。

---

## Task 2: 执行合并

**Files:** 无

- [ ] **Step 1: 在 develop 分支合并 upstream/main**

运行：

```powershell
git merge upstream/main
```

预期：进入合并状态，Git 报告冲突文件。

- [ ] **Step 2: 记录冲突文件清单**

运行：

```powershell
git diff --name-only --diff-filter=U
```

预期清单至少包含：
- `.gitignore`
- `memory-bank/activeContext.md`
- `memory-bank/changelog.md`
- `memory-bank/productContext.md`
- `memory-bank/progress.md`
- `memory-bank/projectBrief.md`
- `memory-bank/systemPatterns.md`
- `memory-bank/techContext.md`
- `agent/go-service/taskersink/membership/memberdata.go`
- `scripts/setup-local-env.ps1`

---

## Task 3: 解决 `.gitignore` 冲突

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 编辑 `.gitignore` 采用上游改动并保留本地规则**

在 `# Build` 段落的 `deps` 行之后新增一行 `3rdparty`，并确保文件末尾以换行结束。最终相关段落如下：

```text
# Build
install/
maafw/*
mxu*
deps
3rdparty
```

- [ ] **Step 2: 标记冲突已解决**

运行：

```powershell
git add .gitignore
```

---

## Task 4: 保留 Memory Bank

**Files:**
- Modify: `memory-bank/*.md`（标记为已解决）

- [ ] **Step 1: 保留本地 Memory Bank 文件**

由于 upstream 已删除这些文件，合并时会出现 add/delete 冲突。使用本地版本：

```powershell
git checkout --ours memory-bank/activeContext.md
git checkout --ours memory-bank/changelog.md
git checkout --ours memory-bank/productContext.md
git checkout --ours memory-bank/progress.md
git checkout --ours memory-bank/projectBrief.md
git checkout --ours memory-bank/systemPatterns.md
git checkout --ours memory-bank/techContext.md
```

- [ ] **Step 2: 标记冲突已解决**

运行：

```powershell
git add memory-bank/
```

---

## Task 5: 解决 `memberdata.go` 并保留本地绕过

**Files:**
- Modify: `agent/go-service/taskersink/membership/memberdata.go`

- [ ] **Step 1: 使用上游版本作为基础**

运行：

```powershell
git checkout --theirs agent/go-service/taskersink/membership/memberdata.go
```

- [ ] **Step 2: 修改 `checkMembership()` 保留本地绕过逻辑**

编辑 `agent/go-service/taskersink/membership/memberdata.go`，将 `checkMembership()` 函数替换为：

```go
// checkMembership performs the full membership check flow.
func checkMembership() *MembershipStatus {
	return &MembershipStatus{
		Tier:                "Local",
		TierCode:            "local",
		TierName:            "Local",
		PlanCode:            "local",
		PlanName:            "Local",
		StartsOn:            "00000000",
		ExpiresOn:           "99991231",
		RemainingDays:       9999,
		AllFeaturesUnlocked: true,
		UnlimitedRuntime:    true,
		IsMember:            true,
	}
}
```

- [ ] **Step 3: 标记冲突已解决**

运行：

```powershell
git add agent/go-service/taskersink/membership/memberdata.go
```

---

## Task 6: 同步续费提醒并确保与本地无限会员兼容

**Files:**
- Create: `agent/go-service/taskersink/membership/renewal_reminder.go`
- Create: `agent/go-service/taskersink/membership/renewal_reminder_test.go`
- Modify: `agent/go-service/taskersink/membership/action.go`

- [ ] **Step 1: 确认上游新增文件已自动带入**

合并后检查文件是否存在：

```powershell
Test-Path agent/go-service/taskersink/membership/renewal_reminder.go
Test-Path agent/go-service/taskersink/membership/renewal_reminder_test.go
```

预期：均为 `True`。如未自动带入，从 `upstream/main` 检出：

```powershell
git checkout upstream/main -- agent/go-service/taskersink/membership/renewal_reminder.go
```

- [ ] **Step 2: 确认 `action.go` 已包含 `maybePrintRenewalReminder` 调用**

合并后 `runRuntimeQuotaCheck` 中应包含：

```go
	maybePrintRenewalReminder(ctx, status)
```

- [ ] **Step 3: 验证续费提醒不会为本地无限会员触发**

`renewal_reminder.go` 中的 `shouldShowRenewalReminder` 已包含 `status.UnlimitedRuntime` 为 `false` 的条件：

```go
func shouldShowRenewalReminder(status *MembershipStatus) bool {
	if status == nil || !status.IsMember || status.UpdateRequired || status.UnlimitedRuntime {
		return false
	}
	...
}
```

由于 `checkMembership()` 返回 `UnlimitedRuntime: true`，续费提醒不会触发。无需额外修改。

---

## Task 7: 处理 `scripts/setup-local-env.ps1` 删除冲突

**Files:**
- Delete: `scripts/setup-local-env.ps1`

- [ ] **Step 1: 跟随上游删除该脚本**

运行：

```powershell
git rm scripts/setup-local-env.ps1
```

---

## Task 8: 检查并标记其他冲突文件

**Files:**
- Modify: `.vscode/settings.json`

- [ ] **Step 1: 确认 `.vscode/settings.json` 冲突**

如有冲突，保留上游新增的 JSONC 格式化配置：

```json
    "[jsonc]": {
        "editor.defaultFormatter": "vscode.json-language-features"
    }
```

- [ ] **Step 2: 标记冲突已解决**

```powershell
git add .vscode/settings.json
```

---

## Task 9: 完成合并提交

**Files:** 无

- [ ] **Step 1: 确认所有冲突已解决**

运行：

```powershell
git diff --name-only --diff-filter=U
```

预期：无输出。

- [ ] **Step 2: 提交合并**

运行：

```powershell
git commit -m 'sync: 合并 upstream/main (v1.6.2) 到 develop' -m '保留本地会员绕过、Memory Bank 与 CI 修复；解决 .gitignore、memberdata.go 等冲突。'
```

---

## Task 10: 编译与测试验证

**Files:**
- Verify: `agent/go-service/...`

- [ ] **Step 1: 在 go-service 目录执行编译**

运行：

```powershell
cd agent/go-service
go build ./...
```

预期：无错误。

- [ ] **Step 2: 执行单元测试**

运行：

```powershell
go test ./...
```

预期：全部通过。

- [ ] **Step 3: 检查 membership 绕过逻辑**

运行：

```powershell
Select-String -Path agent/go-service/taskersink/membership/memberdata.go -Pattern 'func checkMembership'
Select-String -Path agent/go-service/taskersink/membership/memberdata.go -Pattern 'UnlimitedRuntime.*true'
```

预期：`checkMembership()` 函数存在且返回 `UnlimitedRuntime: true`。

---

## Task 11: 最终状态检查

**Files:** 无

- [ ] **Step 1: 确认 Memory Bank 文件存在**

运行：

```powershell
Get-ChildItem memory-bank -Name
```

预期：7 个核心文件全部存在。

- [ ] **Step 2: 确认关键新增文件存在**

运行：

```powershell
Test-Path agent/go-service/common/centerpriority/recognition.go
Test-Path assets/resource/image/LargeEvent/ArkRanger/ArkRangerLogo.png
Test-Path assets/resource/pipeline/RedDotClear/RedDotClearBlaBla.json
```

预期：均为 `True`。

- [ ] **Step 3: 查看合并后的提交日志**

运行：

```powershell
git log --oneline -5 --graph
```

预期：显示合并提交，包含 upstream/main 和 develop 两条线。

---

## 验证标准

- `go build ./...` 无错误
- `go test ./...` 无失败
- `memory-bank/` 中 7 个核心 Markdown 文件均存在
- `agent/go-service/taskersink/membership/memberdata.go` 中的 `checkMembership()` 仍返回本地无限会员状态
- 合并提交已生成，且无未解决的冲突文件

## 回退方案

若合并过程中需要中止：

```powershell
git merge --abort
```

若合并提交后发现错误且需要撤销：

```powershell
git reset --hard HEAD~1
```

若需恢复到合并前状态：

```powershell
git reset --hard backup/develop-before-upstream-sync
```
