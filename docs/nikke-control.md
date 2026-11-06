# NIKKE CLI 控制工具

NIKKE 控制已改为按需使用的 CLI + skill。新聊天不会自动启动 NIKKE MCP，也不会为了加载工具申请管理员权限；只有明确执行 `session` 才会启动控制进程并请求 Windows UAC。

底层仍使用 MaaFramework 的 AAA：`ScreenDC` 截图、`Interception` 鼠标、`Seize` 键盘。地图操作由 skill 根据截图决定；单次主线战斗可交给本地 MDA Pipeline，复用同一控制器，无需启动 MXU 或 Go Agent。

## 环境

需要 Windows、64 位 Python 3.10 或更新版本，以及已安装的 Interception 驱动。控制会话不强制依赖第三方 Python 包，不需要 uv 或 MCP SDK；Pillow 可用时自动生成 JPEG 预览，缺失时仍可使用原始 PNG 完成全部控制操作。

框架 DLL 优先读取仓库 `deps/bin`，缺失时读取 `install/maafw`。指定其他框架时，在命令前加 `--maa-dir`，同一目录须包含 MaaFramework、MaaToolkit、Win32 控制单元及其依赖：

~~~powershell
python E:\Git\MDA\tools\nikke_cli.py --maa-dir 'E:\OtherMaa\bin' status
~~~

## 只读检查

下面两条命令按次退出，不启动操作会话、不申请 UAC，也不发送游戏输入：

~~~powershell
python E:\Git\MDA\tools\nikke_cli.py status
python E:\Git\MDA\tools\nikke_cli.py windows
~~~

`status` 返回框架版本、DLL 路径、驱动访问情况和当前权限；`windows` 返回 NIKKE 窗口的 `window_id`、标题、进程及位置。驱动可访问不代表游戏一定接受输入。

## 启动一次操作会话

~~~powershell
python -u E:\Git\MDA\tools\nikke_cli.py session
~~~

普通权限启动时只提升控制进程，Codex 和终端保留原权限。完成 UAC 后会输出 `{"ok": true, "session": "ready"}`，此后在同一进程中逐行输入命令，复用控制器和这次授权。取消 UAC 会结束启动，不自动重试。

已处于管理员权限时不会再次申请 UAC。`session --no-elevate` 可在诊断时沿用当前权限，但不能解决普通权限控制进程无法激活管理员游戏的问题。

在 Codex 中，skill 通过可交互终端保存 `session_id`，随后向同一终端发送命令；不为每次点击重新启动程序。

| 会话内命令 | 用途 |
| --- | --- |
| `connect` | 候选唯一时连接并激活游戏，返回首张截图 |
| `connect --window-id 0x12345` | 指定窗口；使用实际枚举结果 |
| `observe` | 恢复、激活已连接的游戏并重新截图 |
| `observe --wait-ms 1000` | 等待后再观察，避免连续回传过渡画面 |
| `click 640 360 --snapshot ID` | 根据该截图点击；可加 `--button right` 或 `middle` |
| `drag 900 400 400 400 --snapshot ID` | 拖动；可加 `--duration-ms 600`，有效范围 1～5000，默认 500 |
| `key escape --snapshot ID` | 单键按下后释放；支持字母、数字、空格、回车、Esc、Tab 和方向键 |
| `click 640 360 --snapshot ID --wait-ms 800` | 输入完成后等待，再截一张图；同样支持拖动和按键 |
| `key escape --snapshot ID --no-screenshot` | 输入后不截图；旧标识已消费，下次输入前必须重新观察 |
| `battle --snapshot ID` | 异步托管当前准备页的一次主线战斗 |
| `stop` | 请求停止战斗，等待完成事件后才可继续操作 |
| `status` / `windows` | 查询会话状态或窗口 |
| `disconnect` | 释放控制器，保留 CLI 进程 |
| `help` | 查看命令列表 |
| `quit` / `exit` | 释放控制器并退出会话 |

每行也可以是 JSON，字段沿用控制器接口：

~~~json
{"op":"connect"}
{"op":"click","snapshot_id":"从上一条截图结果取得","x":640,"y":360}
{"op":"press_key","snapshot_id":"从最新截图结果取得","key":"escape"}
{"op":"quit"}
~~~

每条结果都是 JSON 行，会话内命令失败不会自动退出。战斗完成和停止未完成通知也会异步输出 JSON 行。终端自身可能回显命令并附加 ANSI 控制码；管道方式的 stdout 只输出 JSON。

## 查看截图与判断结果

连接、观察和输入后的截图结果包含 `image_path`、`snapshot_id`、图片宽高、原始宽高、截图时间和 `image_changed`。原图保存到 `.cache/nikke-control/cli/<会话标识>/latest.png`，后续截图覆盖它。`image_changed: false` 表示与上一次发布的 PNG 字节完全相同，文件不重写，但仍生成新的截图标识；如果前一张图已经看过且仍在上下文中，就跳过预览和 `view_image`。没有看过或上下文已丢失时，需要查看一次。画面相同不代表输入未执行或动画已停止。

Pillow 可用时，CLI 自动生成同尺寸 JPEG；如果它比 PNG 更小，同一条结果会额外包含 `preview_path`。Codex 优先用 `view_image` 只读取 `preview_path`，没有该字段时读取 `image_path`，无需额外命令或再次截图。PNG 字节去重与预览压缩互相独立，预览失败不会丢失输入结果或有效截图标识。

已有的本地截图也可单独生成预览：

~~~powershell
python E:\Git\MDA\tools\nikke_cli.py preview '实际返回的 image_path'
~~~

该命令只处理本地图片，不启动控制器、不申请 UAC、不重新截图。它使用可选 Pillow，在原图旁覆盖保存 `<原文件名>.preview.jpg`，返回预览绝对路径、宽高和转换前后的字节数。会话截图对应 `latest.preview.jpg`。像素尺寸保持不变，继续使用原截图的标识与坐标。Pillow 不可用或小字不清楚时查看原图，通常不重复加载两个版本；会话已经返回 `preview_path` 时无需再运行预览命令。

`click`、`drag`、`key` 的 `--wait-ms N` 会在输入完成后等待，再截一张图；`observe --wait-ms N` 则在观察前等待。范围 0～10000 毫秒，默认 0。对于已知的移动、加载或界面动画，优先等待后只查看一张结果图，避免刚操作就查看过渡画面，再立即观察一次。

`--no-screenshot`（JSON 为 `capture: false`）可跳过手动输入的即时截图，只返回 `input_status: completed, observation_status: skipped`，不生成新标识。旧标识已经消费，必须等待后 `observe`、查看图片，才能继续输入，不能据此盲目连点。JSON 等待字段为 `wait_ms`；这两个选项不用于 `battle`。

手动模式不持续截图；托管期间由 Tasker 内部截图，结束只发布最终图片。`status` 和战斗等待保持纯文本。移动进度用地标、关卡编号和待处理事项记录，避免重复加载图片。

**覆盖磁盘文件不会删除聊天历史中的图片。** JPEG 减少图片上传字节，保持相同尺寸不保证减少视觉 token；CLI 无权裁剪宿主上下文。长任务仍需宿主执行上下文压缩，不应修改聊天历史文件来删图。上下文压缩的 API 层机制见 [OpenAI 官方文档](https://developers.openai.com/api/docs/guides/compaction)。

输入坐标属于返回图片，长边等比缩放为 1280，标准横屏为 1280×720。框架负责映射回窗口坐标，调用方无需再计算桌面偏移、DPI 或分辨率比例。

每次输入都要求最新、只使用一次的 `snapshot_id`。窗口身份、位置、尺寸或焦点改变后重新观察；鼠标目标被其他窗口遮挡时也会拒绝输入。截图标识不能冻结游戏动画，页面有变化时仍需观察。

| 结果字段 | 含义与处理 |
| --- | --- |
| `input_status: not_sent` | 未提交输入，按错误信息修正 |
| `input_status: completed` | 框架完成输入，查看截图确认游戏效果 |
| `input_status: unknown` | 可能已部分执行，不直接重发；等待底层请求结束后观察 |
| `observation_status: failed` | 截图或图片保存失败；若输入已完成，不代表“没有点击” |
| `observation_status: skipped` | 明确跳过了截图；下一次输入前必须观察并查看图片 |

发生未知结果或回图失败时，CLI 不自动补点。不要同时用 MDA 自动任务和 CLI 控制同一游戏窗口。

## 退出与权限生命周期

完成操作后输入 `quit`，确认 `session: closed` 和进程退出。战斗运行时先 `stop` 并等到 `battle.finished`；底层请求仍在执行时，`quit` 会拒绝退出。stdin 结束会请求停止并等待真实清理，等待超过 10 秒会报告 `session: cleanup_pending` 并继续等待，不能把它当成已关闭。释放顺序为 Tasker → Resource → Controller。外部强制结束进程无法保证原生清理。

CLI 复用 `tools/nikke_mcp_launcher.py` 中的匿名管道与 Windows 提权代码，但不运行 MCP 服务、不导入 MCP SDK，也不监听网络端口。该文件原有的 MCP 入口保留为兼容实现。控制进程日志位于 `.cache/nikke-control/elevated-stderr.log`，框架日志位于 `.cache/nikke-control/logs/`。

## skill 与旧 MCP 配置

- 通用控制说明位于 [.agents/skills/nikke-control/SKILL.md](../.agents/skills/nikke-control/SKILL.md)，仅在实际游戏操作时启动 CLI。
- 本机已有的 `nikke-campaign` skill 已改为使用 CLI，保留地图导航、机关、战斗和清敌策略。
- [.codex/config.toml](../.codex/config.toml) 中的 `mcp_servers.nikke-control.enabled` 设为 `false`，避免新聊天启动服务、加载工具和申请权限。

可运行 `codex mcp get nikke-control --json` 确认 `enabled: false`。配置变更不会强行结束已运行的旧 MCP；客户端重新加载配置或新建聊天后采用新设置。

## 单次主线战斗托管

在已观察的 Normal / Hard 主线准备页发送：

~~~text
battle --snapshot 最新截图标识
~~~

也支持 `{"op":"battle","snapshot_id":"..."}`。命令消费这次截图，立即返回带 `battle_id` 的受理结果，随后由本地流程完成快战或普通自动战斗、跳剧情、结算和已知奖励弹窗。保持当前阵容，不选择下一关、多次战斗 MAX、付费或失败重试。EX 由 skill 排除；需要阅读剧情时使用手动操作。

首次调用才加载 `assets/resource` 和 `tools/nikke_resources` 并创建 Tasker，绑定现有 AAA Controller；同一连接内复用，普通诊断和手动操作不加载战斗资源。复用 MDA 节点时只为本次任务覆盖控制流，原有共享 Pipeline 保持原行为。

运行期间只接受 `status` / `stop`。`status` 返回 `controller_owner`、`battle` 和 `last_battle`，不截图。完成后异步输出：

~~~json
{"type":"battle.finished","battle_id":"本次ID","ok":true,"status":"completed","outcome":"unknown","return_state":"campaign_map","controller_idle":true,"input_status":"completed","observation_status":"completed","snapshot_id":"新ID","image_path":"最终图片绝对路径"}
~~~

`ok` 表示执行及交还正常，胜败看 `outcome`；明确战败回到地图可以是 `ok: true, outcome: lost`。目前缺少真实胜利和快战成功样本，**成功流程返回 `unknown`，不会根据 ESC、Tasker 成功或小地图推定 `won`**。agent 查看最终图，确认敌人消失和地图进度后继续；不要因 `unknown` 直接再战。未提交战斗任务时为 `not_started` / `not_sent`。

`return_state` 区分地图、章节提示、结算、战斗或未知页面。已知遮挡优先于地图交还；章节提示停下由 agent 决定。未知弹窗仍可能需要人工或 agent 恢复。截图或落盘失败保留战斗结果，实际空闲后重新观察即可。

单场总期限 300 秒，资源加载期限 30 秒。`stop` 只受理停止，不保证当前输入已结束；5 秒仍未停稳会输出一次 `battle.stopping`，携带 `reason: stop_pending` 和 `controller_idle: false`，继续隔离资源。Tasker 停止且 Controller 队列排空后才发布 `battle.finished`。前台、身份和窗口几何监测发现变化时停止；已排队输入不能撤回，异常可能为 `input_status: unknown`。不要在等待中发 `observe` 或重新连接。

实现边界和待补的识别证据见 [融合设计及验证记录](superpowers/specs/2026-11-06-nikke-cli-battle-integration-design.md)。

## 验证

无需第三方 Python 包的 CLI、控制器与提权桥接测试：

~~~powershell
python -S -m unittest tools.verify.test_nikke_control tools.verify.test_nikke_mcp_launcher tools.verify.test_nikke_cli tools.verify.test_nikke_battle -v
~~~

此命令会跳过旧 MCP 协议测试。需要验证兼容入口时，使用其声明的 SDK 版本，避免本机其他版本的 MCP 包导致导入错误：

~~~powershell
uv run --no-project --with 'mcp==2.3.0' --with pillow python -m unittest tools.verify.test_nikke_control tools.verify.test_nikke_mcp_launcher tools.verify.test_nikke_cli tools.verify.test_nikke_battle -v
~~~

测试覆盖按需提权、连接复用、命令与 JSON 解析、延后/跳过截图、相同图片去重、过期截图拒绝、图片保存失败后的输入状态、异步战斗接管、停止排空、资源复用、失焦、超时、EOF 清理和真实 stdio。JPEG 测试在 Pillow 可用时检查尺寸、原图保留和失败处理；`-S` 环境跳过转换测试，但验证缺少 Pillow 时的降级。自动化测试不弹出真实 UAC，也不发送游戏输入。

2026-11-06 对已有的 1280×720 截图离线转换，PNG 为 773257 字节，JPEG 为 103413 字节，减少约 86.6%；通过 `view_image` 读取的 Base64 长度与该 JPEG 字节数一致，未转回 PNG。此结果仅说明该样本的文件体积变化，不是游戏交互速度、网络耗时或上下文 token 的实测。

同日 Python 3.12.12 / MCP 2.3.0 / Pillow 13.0.0 的全部 91 项测试通过；Python 3.13.3 `-S` 通过 83 项，跳过八项可选 MCP/JPEG 测试。两个 skill 均通过结构校验。

用本机 DLL 和虚拟控制器回放实际战斗图：

~~~powershell
python -S -m tools.verify.verify_nikke_battle
~~~

它保留实际复合识别、JumpBack、max_hit 和路由，仅用探针模拟页面及输入，验证单场边界、遮挡、原生停止、队列排空和任务覆盖隔离；不证明 OCR、落点或游戏实机效果。

2026-11-06 已在普通权限的 Python 3.13 下使用 `-S` 实测框架 v5.13.1 状态、NIKKE 窗口枚举、交互会话和退出，无 UAC 或游戏输入。既有 AAA 的实机截图记录见 [历史 MCP 设计与验收](superpowers/specs/2026-11-05-nikke-control-design.md)；CLI 的真实提权和游戏点击、拖动、按键仍待实机验收。
