# VOCALOID6 Native MCP

在独立后台进程中调用本机 VOCALOID6 原生 VSM 引擎。MCP 创建并管理自己的工程会话，不接管正在使用的 VOCALOID 编辑器窗口。

## 运行方式

需要 Windows、本机已安装且正常授权的 VOCALOID6、Python 3.11+ 和 .NET 8 SDK/Windows Desktop Runtime。

```powershell
powershell -NoProfile -File .\tools\setup.ps1
```

工作区 MCP 配置已经放在 `.vscode/mcp.json`，服务名为 `vocaloid6-native`。stdio 手动入口：

```powershell
.\.venv\Scripts\python.exe -m vocaloid_bridge
```

这是 MCP 协议入口，等待客户端的 JSON-RPC 消息，不是交互式命令提示符。

## 已安装客户端

本机以下用户级配置已注册 `vocaloid6-native`，不局限于当前工作区：

| 客户端 | 配置位置 |
| --- | --- |
| VS Code Stable | `%APPDATA%/Code/User/mcp.json` |
| VS Code Insiders | `%APPDATA%/Code - Insiders/User/mcp.json` |
| Claude Code | `%USERPROFILE%/.claude.json` |
| Claude Desktop | `%LOCALAPPDATA%/Claude-Data/claude_desktop_config.json` |
| Claude Desktop 第三方模式 | `%LOCALAPPDATA%/Claude-3p/claude_desktop_config.json` |
| Codex | `%USERPROFILE%/.codex/config.toml` |

这些条目均使用 `E:/VC/vocaloid_bridge/.venv/Scripts/python.exe -m vocaloid_bridge`，并显式设置 `VOCALOID_WORKSPACE`、`PYTHONPATH` 为 `E:/VC/vocaloid_bridge`，`PYTHONUTF8` 为 `1`。从其他目录启动时，输出仍写到本项目的 `output`。Codex 的 `tool_timeout_sec` 为 180。

Claude Code 注册时曾报告 Connected；六处配置的启动参数当时均已校验，并从用户主目录完成实际 MCP 握手和 24 个工具发现。本轮工作区服务提供 36 个工具和 108 个结构化操作；既有客户端需要重新加载 MCP 服务才能发现新增工具。没有强制重启客户端或改变登录、模型与其他 MCP 服务。

## 工具

| 功能 | 工具 |
| --- | --- |
| 原生引擎状态 | `vocaloid_status` |
| 完整功能清单、结构化操作与真实接口目录 | `vocaloid_features`, `vocaloid_operations`, `native_api_catalog` |
| 真正新建、打开、保存、关闭工程 | `project_create`, `project_open`, `project_save`, `project_close` |
| 原生格式导入、MIDI 导出 | `project_import`, `project_export_midi` |
| 独立工程副本、恢复、合并 | `project_clone`, `project_revert`, `project_merge` |
| 工程状态、原生对象成员和参数 | `project_status`, `project_members`, `project_get`, `project_set` |
| 精确签名调用、原生数据结构、集合 | `project_call`, `project_value_create`, `project_items` |
| 结构化轨道、音符、曲线和历史 | `project_edit` |
| 原生离线音频、效果与混缩 | `project_audio` |
| 原生歌词、音素、样式与媒体库 | `project_library` |
| 私有剪切、复制与粘贴 | `project_clipboard` |
| 本机声库 | `voicebanks` |
| 原生人声片段合成、音频检查 | `project_render_part`, `audio_inspect` |
| 音符、歌词、曲速、控制曲线、工程 JSON | `score_compose`, `score_replace_notes`, `score_tempo`, `score_curve`, `score_patch`, `score_inspect`, `score_summary` |
| MIDI 读写 | `midi_read`, `midi_write` |

原生对象以会话内 `$ref` 标识。先调用 `project_members` 获取真实属性、参数类型和 `member_id`，再调用其他对象工具；不猜测重载签名。关闭会话后对象引用失效。

完整清单见 [功能矩阵](docs/feature-matrix.md)，运行时也可读取 `vocaloid://features`。`vocaloid_operations` 返回全部结构化操作名及对应文档；用 `domain`、`operation` 定位接口，`include_documentation=true` 读取完整约定。参数见 [乐谱操作](docs/score-operations.md)、[音频操作](docs/audio-operations.md)、[媒体与音素操作](docs/library-operations.md) 和 [原生协议](docs/native-protocol.md)。`native_api_catalog` 可以显示未开放成员及原因；接口可发现不等于功能已经通过验收。

`score_compose` 使用编辑器生成的模板写入音符后，再让原生引擎打开生成的工程。音符时间单位是四分音符拍；`pitch` 可用 MIDI 数字或 `C4`。`lang_id` 为模板声明支持的语言编号。缺省模板引用本机 `asa` 声库，其他声库使用相应模板或原生声库设置接口。

可以直接向已连接 MCP 的模型提出：

> 写一段 8 小节的旋律和歌词，使用本机 asa 声库，创建后台工程，保存 VPR 并合成人声 WAV 到 output，然后关闭这次创建的工程。不要操作我的编辑器窗口。

`write_song` 提示模板和 `vocaloid://workflow` 资源也提供了写歌流程。

## 后台约束

- 只使用原生引擎这一条执行路径，不提供 UI 或其他音源回退。
- 新宿主通过 `CreateProcess` 的 `lpDesktop` 进入私有 Windows desktop，不调用 `SwitchDesktop`。
- 不启动 `VOCALOID6.exe`，不向用户窗口发送输入，不改变用户的播放状态。
- 原生对象全部由宿主的同一 STA 线程使用；子进程归属 kill-on-close Job Object。
- 工程输入可以是显式指定的本机 VPR；输出限定在工作区 `output`，默认不覆盖现有文件。
- 未保存工程需要显式 `discard_changes=true` 才能关闭。原始输入工程不能被覆盖。
- 授权与声库仍由本机 VOCALOID 组件检查，不复制或修改授权数据。

## 验证与范围

```powershell
.\.venv\Scripts\python.exe .\tools\smoke_mcp.py
.\.venv\Scripts\python.exe .\tools\render_demo.py
.\.venv\Scripts\python.exe .\tools\verify_all.py `
	--phoneme-manual-text .\.runtime\VOCALOID6_Reference_Manual_6130_ENG.txt `
	--vsqx-fixture .\.runtime\benben_01\cant_stop\cant_stop.vsqx `
	--vsqx3-fixture .\.runtime\vsqx3-reference.vsqx `
	--ppsf-fixture .\.runtime\radio-miku-gohan-20220311.ppsf
```

本轮 [完整验收回执](artifacts/feature-acceptance-012574702338/summary.json) 为 76 通过、5 失败、2 个缺样本项；36 个工具和 108 个结构化操作均出现过成功调用，但功能语义仍有失败。后续 [定向回执](artifacts/feature-acceptance-6d7fb89e808b/summary.json) 验证了含发声区域的 48/96 kHz 混缩，并确认经典 Singing Skill 重开受到经典轨道身份问题影响。Robot 的实际声音差异、PPSF/VSQX 经典身份往返仍待修复；PPSF V3 需要真实样本。具体逐项状态见 STATUS 和功能矩阵。

原生混缩输出整工程或所选整轨，各分轨保留自己的时长；分轨不使用主效果和主音量自动化。`start_seconds`、`end_seconds` 和 `tail_seconds` 不受此原生入口支持，传入会明确报错。素材属性写入独立的 `property.json`；新建自有素材可在 `.vsclip` 中附加桥接元数据。

当前实测状态见 [STATUS.md](STATUS.md)，未验和受限功能见 [功能矩阵](docs/feature-matrix.md)。PPSF 轨道/声库、高级表现及特殊素材组合仍有缺口；静态音素表不是逐声库能力清单，设备/DAW/界面和授权操作受既定约束限制。VPR 保存成功不等于 WAV 合成成功。

验收生成的工程、原生人声和混音保存在 `output/feature-012574702338-*` 等独立批次，路径及音频测量见逐项回执。每次运行使用独立名称，不覆盖已有工程或音频。无样本参数的 `VOCALOID6: full feature acceptance` 任务会将依赖样本的用例标为阻塞。

操作目录修改后运行 `tools/generate_operation_catalog.py`，用 `--check` 检查它与原生 dispatch、文档是否一致。`tools/check_host_isolation.py` 是双后台宿主音频缓存隔离回归。宿主从私有构建副本运行，并使用独立 VSM 缓存命名空间，不加载用户前台编辑器的缓存目录。

实现依据与调用约定见 `docs/native-protocol.md`、`docs/project-format.md` 和 `docs/architecture.md`。

用户提供的 AI-VOCALOID-MCP 参考实现及对应关系记录在 `docs/references.md`。
