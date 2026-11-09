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

Claude Code 注册时曾报告 Connected；六处配置的启动参数当时均已校验，并从用户主目录完成实际 MCP 握手和 24 个工具发现。当前源码 0.16.0 提供 37 个工具和 125 个结构化操作，独立 stdio 客户端的定向测试已通过。本对话现有连接仍报告 Python MCP 0.4.0；其运行中的原生宿主此前经比对为 0.5.0 构建，尚未载入 0.16.0。重新连接后应核对版本；没有强制重启客户端或改变登录、模型与其他 MCP 服务。

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
| 原生离线音频、效果、混缩和独立设备传输 | `project_audio` |
| MIDI 输入设备枚举和音符录制 | `project_midi` |
| 原生歌词、音素、样式与媒体库 | `project_library` |
| 私有剪切、复制与粘贴 | `project_clipboard` |
| 本机声库 | `voicebanks` |
| 原生人声片段合成、音频检查 | `project_render_part`, `audio_inspect` |
| 音符、歌词、曲速、控制曲线、工程 JSON | `score_compose`, `score_replace_notes`, `score_tempo`, `score_curve`, `score_patch`, `score_inspect`, `score_summary` |
| MIDI 读写 | `midi_read`, `midi_write` |

原生对象以会话内 `$ref` 标识。先调用 `project_members` 获取真实属性、参数类型和 `member_id`，再调用其他对象工具；不猜测重载签名。关闭会话后对象引用失效。

完整清单见 [功能矩阵](docs/feature-matrix.md)，运行时也可读取 `vocaloid://features`。`vocaloid_operations` 返回全部结构化操作名及对应文档；用 `domain`、`operation` 定位接口，`include_documentation=true` 读取完整约定。参数见 [乐谱操作](docs/score-operations.md)、[音频操作](docs/audio-operations.md)、[MIDI 录制](docs/midi-recording.md)、[媒体与音素操作](docs/library-operations.md) 和 [原生协议](docs/native-protocol.md)。`native_api_catalog` 可以显示未开放成员及原因；接口可发现不等于功能已经通过验收。

`score_compose` 使用编辑器生成的模板写入音符后，再让原生引擎打开生成的工程。音符时间单位是四分音符拍；`pitch` 可用 MIDI 数字或 `C4`。`lang_id` 为模板声明支持的语言编号。缺省模板引用本机 `asa` 声库，其他声库使用相应模板或原生声库设置接口。

按当前 AI 工作流，`track.create` 未指定 `type` 时创建 `MidiAi` 轨道；它不会代替调用者挑选声库，新建片段合成前用 `voicebanks` 和 `voice.set` 显式选择已安装的 AI 声库。旧调用若需要传统轨，需显式传入 `type=Midi`；此默认值与 0.3.0 不同。

可以直接向已连接 MCP 的模型提出：

> 写一段 8 小节的旋律和歌词，使用本机 asa 声库，创建后台工程，保存 VPR 并合成人声 WAV 到 output，然后关闭这次创建的工程。不要操作我的编辑器窗口。

`write_song` 提示模板和 `vocaloid://workflow` 资源也提供了写歌流程。

## 后台约束

- 只使用原生引擎这一条执行路径，不提供 UI 或其他音源回退。
- 新宿主通过 `CreateProcess` 的 `lpDesktop` 进入私有 Windows desktop，不调用 `SwitchDesktop`。
- 不启动 `VOCALOID6.exe`，不向用户窗口发送输入，不改变用户交互编辑器的播放状态。
- 原生对象全部由宿主的同一 STA 线程使用；子进程归属 kill-on-close Job Object。
- 设备传输明确选择枚举到的设备 ID，只管理 MCP 自己的音频引擎；准备期间先释放传输再修改所属工程。
- MIDI 设备录制需要显式设备 ID 与名称；独立虚拟 WinMM 输入的真实回调已验，事件流和虚拟输入均不代表物理硬件录制已验。同步模式仅使用本会话的播放时钟。
- `track.freeze` 使用会话自有缓存；保存和克隆输出未冻结的作者状态，关闭清理缓存。
- 工程输入可以是显式指定的本机 VPR；输出限定在工作区 `output`，默认不覆盖现有文件。
- 未保存工程需要显式 `discard_changes=true` 才能关闭。原始输入工程不能被覆盖。
- 授权与声库仍由本机 VOCALOID 组件检查，不复制或修改授权数据。

## 验证与范围

公开 PPSF3 样本可通过下列命令保存到被忽略的运行目录；工具会记录作者页面和下载来源，不将歌曲纳入源码。

```powershell
.\.venv\Scripts\python.exe .\tools\fetch_public_ppsf_fixture.py --source monologue
```

```powershell
.\.venv\Scripts\python.exe .\tools\smoke_mcp.py
.\.venv\Scripts\python.exe .\tools\render_demo.py
.\.venv\Scripts\python.exe .\tools\verify_all.py `
	--phoneme-manual-text .\.runtime\VOCALOID6_Reference_Manual_6130_ENG.txt `
	--vsqx-fixture .\.runtime\benben_01\cant_stop\cant_stop.vsqx `
	--vsqx3-fixture .\.runtime\vsqx3-reference.vsqx `
	--ppsf-fixture .\.runtime\radio-miku-gohan-20220311.ppsf `
	--ppsf3-fixture .\.runtime\public-ppsf3-javawock-download\Monologue.ppsf
```

上轮 [完整验收回执](artifacts/feature-acceptance-012574702338/summary.json) 为 76 通过、5 失败、2 个缺样本项。0.2.1 已取得 Robot 缓存修复、真实 PPSF3、Take、三个 AI VoiceColor 参数以及项目完整性保护的定向证据；[生命周期与素材回归](artifacts/feature-acceptance-983dee33baea/summary.json) 为 6 项通过。没有把历史套件改称本轮全部通过；结果与剩余环境依赖见 [STATUS](STATUS.md) 和 [功能矩阵](docs/feature-matrix.md)。

0.3.0 的 [整合定向回执](artifacts/feature-acceptance-26a71f9b1dc5/summary.json) 验证正式冻结、119 项目录和静音设备传输。未知字段、固定嵌套对象和额外资源的保留，以及删除/重建、撤销/重做的实体关联，另有独立回执。详见 [工程保留](docs/project-preservation.md)、[设备传输](docs/transport.md) 和 [轨道冻结](docs/track-freeze.md)；这些范围不等于任意扩展格式、声库、设备与效果组合都已验证。

0.4.0 的 [MIDI 事件流回执](artifacts/feature-acceptance-878d0c135692/summary.json) 覆盖六个 MIDI 操作；[独立回执](artifacts/midi-synthetic-3fa675486b20.json) 验证速度变化和静音 transport 同步。轨道、片段、音符复制保留扩展数据及历史的定向回执为 `artifacts/feature-acceptance-647c107fc2bd/preservation.duplicates.json`；其后扩展拆合的进展见 0.5.0 回执。

0.5.0 的 [定向回执](artifacts/feature-acceptance-e57fec059ac3/summary.json) 覆盖 AI 扩展字段的剪切、跨工程粘贴、合并、目标旧历史和普通工程兼容；音符及片段拆合另有 [定向回执](artifacts/feature-acceptance-a4a1a5dc7d8d/summary.json)。不透明额外资源的跨工程迁移、物理 MIDI 设备和 DAW 宿主仍有待验证的边界，详见 [扩展迁移](docs/archive-transfer.md) 和 [DAW IPC 调查](docs/daw-ipc.md)。

0.6.0 的 [全局字段合并回执](artifacts/feature-acceptance-5a2c12f87c28/summary.json) 覆盖直接及受测嵌套 root/master 扩展的合并、歧义和冲突预检、历史与保存重开；[独立虚拟 MIDI 输入回执](artifacts/midi-owned-78935c45c6f9.json) 覆盖真实 WinMM 回调、录音和端口清理，不等于物理设备验收。

0.7.0 的 [定向回执](artifacts/feature-acceptance-a2ec5efb0ad1/summary.json) 覆盖速度事件未知字段、剪贴板歧义预检、工程不透明资源合并及冲突与历史；[合成 ZIP 检查](artifacts/archive-export-4717c45e9a45.json) 验证缩小阈值下的数量、大小和路径冲突保护。受测范围不等于任意扩展格式和资源组合。

0.8.0 的 [定向回执](artifacts/feature-acceptance-5f7c71ba55ed/summary.json) 覆盖 AI 剪贴板的工程级不透明资源、tempo 扩展合并及拍号扩展编辑；旧测试仍按原守卫预期失败，更新后的 [单项回执](artifacts/feature-acceptance-0f5180183d62/summary.json) 通过。当时拍号扩展合并、原生音频资源归属、物理 MIDI 和实际 DAW 隔离仍待处理；后续进展见下文。

0.9.0 的 [定向回执](artifacts/feature-acceptance-b0b2d367967f/summary.json) 覆盖拍号扩展合并、控制器事件扩展编辑、受测音频轨资源迁移，以及扩展工程的原生人声、MIDI 导出与离线混缩。其他控制器扩展迁移、音频组合、物理 MIDI 和实际 DAW 隔离仍待处理。

0.10.0 的 [定向回执](artifacts/feature-acceptance-6cc1fd525f8e/summary.json) 覆盖控制器扩展的复制拆合、重叠冲突回滚、扩展工程独立离线音频和私有素材操作；[普通音频事务回执](artifacts/feature-acceptance-eb4111329c4f/summary.json) 验证导入、编辑和撤销重做。控制器跨工程扩展迁移和扩展工程音频写入仍有保护边界，详见 [STATUS](STATUS.md)。

0.11.0 的 [AI 素材回执](artifacts/feature-acceptance-39ed0d000904/summary.json) 覆盖受测片段及音符未知字段的捕获、导入、旧历史、保存与重开；[扩展工程静音传输回执](artifacts/feature-acceptance-6667cde9784c/preservation.archive_transport.json) 验证私有快照播放和源工程保护。普通工程效果器原生撤销历史另见 [定向结果](artifacts/feature-acceptance-f97d35cd5451/audio.effect_history.json)；该批次中的两个测试失败及后续修正均保留记录。

0.12.0 的 [定向回执](artifacts/feature-acceptance-b07ec74aa41d/summary.json) 验证音高半开区间边界、纯元数据和不透明资源合并、原生撤销历史及相关回归；[扩展目标及最高速度边界回执](artifacts/feature-acceptance-fc6a72130b1c/summary.json) 进一步验证源保护、冲突和历史。扩展素材属性更新的自动审查拦截、扩展时间编辑和音符数组未知字段边界仍在 [STATUS](STATUS.md) 中记录。

0.13.0 的 [定向回执](artifacts/feature-acceptance-1de6c1d0abc4/summary.json) 覆盖受限 AI 扩展工程时间插入/删除、`directPitches` 项未知字段往返、原生历史及控制器/音频保护；[混合扩展回执](artifacts/feature-acceptance-97ee96429bd9/summary.json) 验证音高和控制器字段共同保存。自动生成事件、跨工程点迁移及扩展音频写入等范围仍有边界，详见 [STATUS](STATUS.md)。

0.14.0 的 [定向回执](artifacts/feature-acceptance-970ae8c4e0d2/summary.json) 覆盖受测音高项扩展的音符/片段复制、原生速度事件碰撞覆盖、扩展事件地图未变化时的时间编辑及保留守卫。[隔离素材探针](artifacts/feature-acceptance-39dc398383e1/summary.json) 观察到原生属性保存删除 `property.json` 中的未知字段；带归档元数据的素材更新守卫保持不变。

0.15.0 的 [定向回执](artifacts/feature-acceptance-5b8f6372f11d/summary.json) 验证受测主音量事件未知字段、时间插入的速度/拍号事件移动以及音高项轨道复制与身份保持操作；首轮两项测试失败在 [复验](artifacts/feature-acceptance-17fec2e1ace1/summary.json) 中按 AI 轨和原生空列表序列化修正后通过。普通素材属性未知字段仍有实际丢失风险，事务方案和审查守卫的边界见 [STATUS](STATUS.md)。

0.16.0 的 [定向回执](artifacts/feature-acceptance-e8eb9b6496cb/summary.json) 为 16 个功能用例及清理共 17 通过，覆盖受测轨道音量/声像项未知字段及部分 tempo/拍号扩展时间删除；[独立生命周期](artifacts/mcp-smoke-acbdb340d53d.json) 通过且前台句柄不变。普通素材属性更新仍会丢失受测未知字段，音高项删除及先前受审查约束的守卫保持原位，详见 [STATUS](STATUS.md)。

原生混缩输出整工程或所选整轨，各分轨保留自己的时长；分轨不使用主效果和主音量自动化。`start_seconds`、`end_seconds` 和 `tail_seconds` 不受此原生入口支持，传入会明确报错。素材属性写入独立的 `property.json`；新建自有素材可在 `.vsclip` 中附加桥接元数据。

此前本机 Dse=0、Dnn=21；经典 VPR 打开前检查已知类型转换条件，原生保存若丢失身份则在发布前报错，已有输出保持。用户选择仅使用 AI 声库，未安装经典试用。静态音素表不是逐声库能力清单，设备/DAW 需要对应环境；VPR 保存成功不等于 WAV 合成成功。

验收生成的工程、原生人声和混音保存在 `output/feature-012574702338-*` 等独立批次，路径及音频测量见逐项回执。每次运行使用独立名称，不覆盖已有工程或音频。无样本参数的 `VOCALOID6: full feature acceptance` 任务会将依赖样本的用例标为阻塞。

操作目录修改后运行 `tools/generate_operation_catalog.py`，用 `--check` 检查它与原生 dispatch、文档是否一致。`tools/check_host_isolation.py` 是双后台宿主音频缓存隔离回归。宿主从私有构建副本运行，使用独立 VSM 缓存命名空间和零合成结果缓存，不加载用户前台编辑器的缓存目录。渲染返回原生完成观察值；内部合成固定要求 44100 Hz，混缩输出率可独立选择。

实现依据与调用约定见 `docs/native-protocol.md`、`docs/project-format.md` 和 `docs/architecture.md`。

用户提供的 AI-VOCALOID-MCP 参考实现及对应关系记录在 `docs/references.md`。
