# 同步 upstream/main (v1.6.2) 到 develop 分支

## 1. 目标与范围

将 `upstream/main`（commit `4ba88f2`，tag `v1.6.2`）的 44 个提交合并到当前 `develop` 分支（commit `016b8ec`），保留本地 develop 的关键改动（会员绕过、Memory Bank、CI 修复），手动解决合并冲突，并通过编译与单元测试验证。

## 2. 涉及的改动领域

### 2.1 上游新增/修改

- **Go 服务层**：新增 `centerpriority` 通用识别器、续费提醒逻辑、竖屏检测增强、魔方强化与循环室升级动作
- **资源文件**：新增 ARK RANGER 大活动、BlaBla/音游红点、战斗角色选择等图片模板
- **Pipeline**：新增/修改红点清除、大活动、战斗、推图、咨询、竞技场、日常奖励等流程
- **本地化**：`assets/locales` 中英文文本更新
- **工程配置**：`.gitignore`、`.vscode/settings.json`、`.github/workflows/install.yml`

### 2.2 本地需保留

- `memory-bank/` 目录
- `checkMembership()` 本地无限会员绕过逻辑
- CI 修复提交

## 3. 冲突处理策略

| 冲突文件 | 处理方式 |
|---------|---------|
| `.gitignore` | 采用上游新增 `3rdparty` 忽略项 + 末尾换行修正，保留本地其他规则 |
| `memory-bank/*` | 保留本地新增的全部 Memory Bank 文件 |
| `agent/go-service/taskersink/membership/memberdata.go` | 合并上游新增的结构/辅助函数，保留 `checkMembership()` 本地绕过逻辑 |
| `agent/go-service/taskersink/membership/renewal_reminder.go` | 同步上游新增文件，但确保本地无限会员状态不触发续费提醒 |
| `scripts/setup-local-env.ps1` | 上游已删除，跟随上游删除 |

## 4. 实施步骤

1. 确认工作区干净：`git status`
2. 在 `develop` 分支执行合并：`git merge upstream/main`
3. 按第 3 节策略手动解决冲突
4. 编译验证：在 `agent/go-service` 运行 `go build ./...`
5. 单元测试验证：在 `agent/go-service` 运行 `go test ./...`
6. 检查 `memory-bank/` 目录仍然存在
7. 检查会员绕过逻辑仍然生效
8. 提交合并结果

## 5. 验证标准

- `go build ./...` 无错误
- `go test ./...` 无失败
- `memory-bank/` 中 6 个核心 Markdown 文件均存在
- `agent/go-service/taskersink/membership/memberdata.go` 中的 `checkMembership()` 仍返回本地无限会员状态

## 6. 回退方案

若合并过程中需要中止：

```powershell
git merge --abort
```

若合并提交后发现错误且需要撤销：

```powershell
git reset --hard HEAD~1
```

## 7. 决策记录

- **同步方式**：方案 A（直接在 develop 分支 merge）
- **会员验证冲突**：保留本地绕过逻辑，不恢复联网验证
- **Memory Bank 冲突**：保留本地新增文件，不跟随上游删除
