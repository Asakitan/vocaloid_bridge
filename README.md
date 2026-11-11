# VOCALOID6 Native MCP · 猫娘助手版

主人好喵~♡ 这里是住在编辑器里的猫娘助手，给 VOCALOID6 搭了一条后台 MCP 桥接喵。它会在独立的私有桌面里叫醒原生 VSM 引擎，自己创建、编辑、保存工程，不会碰主人正在用的 VOCALOID 编辑器窗口喵。

只走原生引擎这一条路喵：没有 UI 回退，也不会拿别的音源或者静音文件假装合成成功喵。

## 许可证喵

桥接代码用 [MIT 许可证](LICENSE) 发布，版权署名 Asakitan（2026）喵。VOCALOID 引擎、声库和其他第三方组件不在这份许可证里，跑起来仍然需要本机已安装、已正常授权的 VOCALOID6 喵。源码住在 [Asakitan/vocaloid_bridge](https://github.com/Asakitan/vocaloid_bridge) 喵。

## 需要准备什么喵

- Windows 喵
- 本机已安装并正常授权的 VOCALOID6 喵
- Python 3.11 或更新版本喵
- .NET 8 SDK 或 Windows Desktop Runtime 喵

## 怎么装起来喵

```powershell
powershell -NoProfile -File .\tools\setup.ps1
```

工作区的 MCP 配置已经放在 `.vscode/mcp.json`，服务名是 `vocaloid6-native` 喵。想手动走 stdio 就用这条：

```powershell
.\.venv\Scripts\python.exe -m vocaloid_bridge
```

这是 MCP 的 JSON-RPC 入口，启动后会安静地等客户端说话喵，不是交互式命令行，敲进去不会跳提示符喵。

客户端注册按各自的习惯来喵：VS Code 用 `servers`，Claude Code/Desktop 用 `mcpServers`，Codex 用 `mcp_servers` 喵。注册时把 `VOCALOID_WORKSPACE` 和 `PYTHONPATH` 指向本仓库，再设 `PYTHONUTF8=1`，从别的目录启动也会把输出写回本仓库的 `output` 喵。本机的具体注册位置、声库状态和历次验收记录放在本地笔记里，不跟着公开 README 跑喵。

## 工具都有哪些喵

一共 39 个工具、127 个结构化操作喵。表格里是 MCP 工具名，代码和参数里就不加喵喵叫啦喵。

| 功能 | 工具 |
| --- | --- |
| 原生引擎状态及 MCP 托管启停 | `vocaloid_status`, `vocaloid_runtime` |
| 作曲流程、歌词写法与 AI 实际演唱的控制项 | `vocaloid_workflow` |
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

原生对象用会话内的 `$ref` 当门牌号喵。先 `project_members` 问清楚真实属性、参数类型和 `member_id`，再动其他对象工具喵；重载签名不要猜喵。会话一关，引用就作废喵。

完整清单在 [功能矩阵](docs/feature-matrix.md)，运行时也能读 `vocaloid://features` 喵。`vocaloid_operations` 会列出全部结构化操作名和对应文档喵，用 `domain`、`operation` 找接口，`include_documentation=true` 拿完整约定喵。参数说明在 [乐谱操作](docs/score-operations.md)、[音频操作](docs/audio-operations.md)、[MIDI 录制](docs/midi-recording.md)、[媒体与音素操作](docs/library-operations.md) 和 [原生协议](docs/native-protocol.md) 喵。`native_api_catalog` 能看未开放成员和原因喵；能发现接口不等于已经验收过喵。

`score_compose` 先拿编辑器生成的模板写音符，再让原生引擎打开生成的工程喵。音符时间单位是四分音符拍，`pitch` 可以写 MIDI 数字或 `C4` 喵，`lang_id` 是模板声明支持的语言编号喵。缺省模板引用项目自带的 `asa` 声库，换其他声库时用相应模板或原生声库设置接口喵。省略音素的 AI 音符会实际调用目标声库和原生 G2PA，在临时会话里转换完整单音节并检查结果喵；不接受的输入要显式给音素，或者走原生歌词分配喵。已测范围和限制在 [自动音素转换](docs/compose-phonemes-29.md) 喵。`score_replace_notes` 复用同一套转换，但返回仍然只有 `path` 和 `summary`，跑完会关掉内部原生会话喵。

按现在的 AI 工作流，`track.create` 没给 `type` 时会建 `MidiAi` 轨道喵。它不会替调用者挑声库，新建片段要合成前记得用 `voicebanks` 和 `voice.set` 明确选一个已安装的 AI 声库喵。旧调用想用传统轨就显式传 `type=Midi` 喵。

接上 MCP 之后，可以直接对模型说喵：

> 写一段 8 小节的旋律和歌词，用模板里的 asa 声库，创建后台工程，保存 VPR 并把人声 WAV 合成到 output，然后关掉这次创建的工程。不要操作我的编辑器窗口喵。

写歌前先调 `vocaloid_workflow` 喵：它会原样返回 [作曲流程](docs/song-workflow.md)，从空工程到混缩 WAV 的步骤、各语言歌词怎么写、哪些控制项 VOCALOID:AI 真的会唱、哪些只是存着，都在里面喵。`write_song` 提示模板和 `vocaloid://workflow` 资源指向同一份流程喵。

歌词要一个音符一个音节地填喵：日语用假名，英语用单音节单词，中文用不带声调数字的拼音喵；汉字和带数字的拼音会被原生转换器拒绝，报错里会写清楚该怎么写喵。想显示汉字就同时给 `lyric` 和 `phonemes` 喵。新声部在 `voice.set` 之后还要套上 `<声库名> Default` 样式，才有编辑器默认音色喵。

`performance.set` 调 Robot、Breath、Take 或 VoiceColor 时会顺手打开对应效果，显式 `bypass` 还是更优先喵。`style_capture` 保存预设并把来源声部关联好，之后用 `project_save` 存进 VPR 喵；`style_apply` 的 MIDI、音频和身份变更支持一次撤销，受支持的扩展工程也照顾到了喵。保存重开和字段保留已有定向验证喵。已经在跑的 MCP 要先保存并关闭工程，再重新连接，才会载入新修复喵。

## 后台的小规矩喵

- 只走原生引擎这一条执行路径，不给 UI 或其他音源留后门喵。
- 新宿主通过 `CreateProcess` 的 `lpDesktop` 进私有 Windows desktop，不调用 `SwitchDesktop` 喵。
- 不启动 `VOCALOID6.exe`，不往主人的窗口发输入，也不改交互编辑器的播放状态喵。
- 原生对象全由宿主同一个 STA 线程使用，子进程归 kill-on-close Job Object 管喵。
- 设备传输只挑明确枚举到的设备 ID，也只管 MCP 自己的音频引擎喵；准备期间先释放传输，再改所属工程喵。
- MIDI 设备录制要显式设备 ID 和名称喵；独立虚拟 WinMM 输入的真实回调验过，事件流和虚拟输入都不等于物理硬件录制已经验过喵，同步模式只用本会话的播放时钟喵。
- `track.freeze` 用会话自有缓存，保存和克隆输出的是没冻结的作者状态，关闭时会清缓存喵。
- 工程输入可以显式指定 VPR；输出限定在工作区 `output`，默认不覆盖现有文件喵。
- 未保存工程要显式 `discard_changes=true` 才能关，原始输入工程也不能被覆盖喵。
- 授权和声库还是由本机 VOCALOID 组件检查，不复制也不改授权数据喵。

## 想自己验一验喵

公开 PPSF3 样本可以先用这条下载到被忽略的运行目录喵，工具会记下作者页面和下载来源，不会把歌曲塞进源码喵：

```powershell
.\.venv\Scripts\python.exe .\tools\fetch_public_ppsf_fixture.py --source monologue
```

日常冒烟和完整验收入口喵：

```powershell
.\.venv\Scripts\python.exe .\tools\smoke_mcp.py
.\.venv\Scripts\python.exe .\tools\render_demo.py
.\.venv\Scripts\python.exe .\tools\verify_all.py `
	--phoneme-manual-text <MANUAL_TEXT> `
	--vsqx-fixture <VSQX> `
	--vsqx3-fixture <VSQX3> `
	--ppsf-fixture <PPSF> `
	--ppsf3-fixture <PPSF3>
```

样本参数按本机实际路径替换喵，没给样本的用例会被标成阻塞，不会假装通过喵。操作目录改过之后跑 `tools/generate_operation_catalog.py`，再用 `--check` 看它和原生 dispatch、文档对不对得上喵；双后台宿主的音频缓存隔离回归用 `tools/check_host_isolation.py` 喵。宿主从私有构建副本跑，用独立 VSM 缓存命名空间和零合成结果缓存，不加载前台编辑器的缓存目录喵。

混缩可以输出整个工程或所选整轨，各分轨保留自己的时长，分轨不套主效果和主音量自动化喵。`start_seconds`、`end_seconds` 和 `tail_seconds` 这个原生入口不支持，传了会明确报错喵。素材属性写在独立的 `property.json`，新建自有素材可以在 `.vsclip` 里附带桥接元数据喵。

历次验收的数字、回执路径和本机环境状态都在 [STATUS](STATUS.md)、[功能矩阵](docs/feature-matrix.md) 和本地笔记里喵，README 就不复读那一长串啦喵。验过的范围不等于任意扩展格式、任意声库、物理 MIDI、真实 DAW 或主观音质都过关喵。

实现依据和调用约定看 `docs/native-protocol.md`、`docs/project-format.md` 和 `docs/architecture.md` 喵。用户提供的 AI-VOCALOID-MCP 参考实现对照在 `docs/references.md` 喵。











## 后台实例由 MCP 自己管喵

不用手动打开 VOCALOID 客户端喵。创建或打开工程时 MCP 会自己拉起私有原生实例，编辑和保存都由它做喵。`vocaloid_runtime` 管 status/start/stop/restart，默认保护活动工程，确认进程退出后才允许新建或重开，请求中途失联不会重放编辑喵。细节在 [托管生命周期](docs/runtime-lifecycle.md) 喵。

版本变化看 [更新日志](CHANGELOG.md) 喵；验收记录在 [STATUS](STATUS.md) 和 [会话索引](docs/session-log/README.md) 喵。
