# 当前状态

日期：2026-11-10。版本：0.8.0。完整目标继续进行，不把受测范围扩大为所有输入与环境组合。

会话 09：用户明确选择仅使用 VOCALOID:AI 声库；不安装经典声库试用，继续扩展 AI 工程编辑及后台设备能力。
未指定类型的 `track.create` 默认改为 `MidiAi`；空工程到显式选声、编辑、保存重开和合成的定向验证见 `artifacts/feature-acceptance-32f1c9da5151/summary.json`。显式 `Midi` 类型及旧工程保护保留。

会话 10：带未知实体字段的音符及片段拆合、冲突回滚和历史有定向 MCP 验证；AI 剪贴板剪切/迁移、工程合并及旧历史、MIDI 错误回调的定向检查通过。DAW 固定命名管道隔离和真实 MIDI 硬件仍待验证。

会话 11：源 root/master 的直接与受测嵌套未知字段可在受控合并中保留，支持冲突预检及合并历史；独立虚拟 MIDI 输入的实际 WinMM 回调和清理通过。随机合成管道的同 profile 双向通信已观察，实际插件隔离仍待验证。

会话 12：受测速度事件未知字段支持编辑、历史和重开；剪贴板粘贴先验证独立候选；轨道合并支持受测不透明资源的冲突保护和历史。自有合成 DLL 的静态导入映射实验通过，实际插件隔离仍待验证。

会话 13：AI 剪贴板选择迁移工程级不透明资源；速度事件扩展按 tick 合并；拍号事件扩展支持编辑与历史。合成 ANSI 探针观察到动态解析、其他模块和初始化时序绕过静态 IAT 修改，实际插件隔离仍待验证。

## 当前入口与实测

- 37 个 MCP 工具，68 个乐谱、16 个音频、30 个素材、5 个剪贴板和 6 个 MIDI 录制操作，共 125 个。创建、打开、编辑、保存、关闭、克隆和恢复保留。
- `project_midi` 提供设备枚举、显式设备或事件流录制、状态、停止和取消；事件流的音符、速度映射、保存重开与静音 transport 同步已验。独立虚拟输入已触发实际 WinMM 回调；输入错误通知、回调故障和溢出的提交保护另有逻辑测试。
- 新增 `devices` 与 `transport_prepare/status/play/stop/seek/release`：明确选择设备，原生 VAE 独立播放；不改系统默认设备或用户编辑器。DirectSound 静音时钟、停止、异步定位、释放后保存、关闭自动释放通过。
- 新增 `track.freeze/freeze_state/unfreeze`：只持有会话自有缓存；修正预送时基、多片段范围和重复音量/声像处理。保存与克隆写出原始作者状态，冻结缓存不持久化。多片段、非零起点、Gain 和音量自动化的受测混音差异约 0.054%。
- 修复原生保存/克隆丢弃未知工程数据：保留 root/master/track/part/note 未知字段、固定嵌套对象字段，以及额外 ZIP 资源；仅覆盖未知键，不恢复旧的已知值。原生实体通知和真实历史边界防止删除重建时元数据错贴。
- 未知数据覆盖包括已验证的重排、更名、音符移动/修改、轨道/片段/音符复制和 AI 剪贴板剪切/跨工程粘贴、AI 工程合并、音符及片段拆合、速度与拍号事件扩展、受测不透明资源的剪贴板与合并迁移、删除同值新建、撤销/重做、参数编辑、保存重开，以及源关闭后的克隆。其他数组、拍号扩展合并和原生音频资源迁移仍有明确限制。
- 0.2.1 的 Robot 零结果缓存修复、19 个音符表现字段、VoiceColor 适用性、Take/Breath/AI VoiceColor 声音证据和真实 PPSF3 样本继续保留。

## 本轮证据

构建：0 警告、0 错误。只运行改动相关检查，未重跑完整历史套件。

| 范围 | 回执 | 结果 |
| --- | --- | --- |
| 0.8.0 独立 stdio 状态与工具发现 | `artifacts/stdio-v080-status-6b5f065e679c.json` | 版本 0.8.0、37 工具、原生后台 |
| 0.8.0 生命周期烟雾测试 | `artifacts/mcp-smoke-129fd1680c28.json` | 创建、修改、保存、重开、音符往返；前台窗口未改变 |
| 剪贴板资源、拍号与速度扩展合并 | `artifacts/feature-acceptance-5f7c71ba55ed/summary.json` | 13 通过、1 个旧 guard 预期失败，含清理；旧预期随后修正 |
| 更新后的速度扩展测试 | `artifacts/feature-acceptance-0f5180183d62/summary.json` | 定向用例与清理通过，含来源和目标扩展、合并及撤销 |
| 补充剪切粘贴与原生音频成员碰撞检查 | `artifacts/feature-acceptance-9cc33036cca5/summary.json` | 定向用例与清理通过；碰撞前目标状态及原生 WAV 保持 |
| 自有合成 DLL 的 ANSI 静态槽与绕过边界 | `artifacts/probe-iat-ansi-boundary.txt` | 静态调用命中；动态解析、第二模块和加载初始化不受该补丁覆盖 |
| 0.7.0 独立 stdio 状态与工具发现 | `artifacts/stdio-v070-status-0dd9be424fba.json` | 版本 0.7.0、37 工具、0 会话 |
| 剪贴板预检、资源合并、速度扩展及相关回归 | `artifacts/feature-acceptance-a2ec5efb0ad1/summary.json` | 10 通过，含清理；无前台切换 |
| 导出 ZIP 数量、大小和路径冲突 | `artifacts/archive-export-4717c45e9a45.json` | 缩小阈值的合成验证通过 |
| 自有 DLL 的合成管道静态导入映射 | `artifacts/probe-appcontainer-iat-controls-acl.txt` | 同 profile 收发及负对照已观察；非实际插件证明 |
| 0.6.0 独立 stdio 状态与工具发现 | `artifacts/stdio-v060-status-1679c32d6429.json` | 版本 0.6.0、37 工具、0 会话 |
| root/master 扩展合并、歧义预检及旧历史 | `artifacts/feature-acceptance-5a2c12f87c28/summary.json` | 2 通过，含清理 |
| 嵌套扩展合并与历史 | `artifacts/feature-acceptance-28ce06be4e32/summary.json` | 2 通过，含清理；先于整合并预检 |
| 全局合并与既有旧历史、音符拆合回归 | `artifacts/feature-acceptance-818d9fb68a28/summary.json` | 4 通过，含清理；先于嵌套预检改动 |
| 自有虚拟 MIDI 输入、回调、编辑和清理 | `artifacts/midi-owned-78935c45c6f9.json` | 通过；物理设备未验 |
| 本对话旧连接的 AI 扩展轨道粘贴 | `artifacts/live-mcp-transfer-1794244477025.json` | 通过；Python 0.4.0、原生宿主为 0.5.0 构建 |
| 随机合成 AppContainer 管道服务端和对端 | `artifacts/probe-appcontainer-server.txt`、`artifacts/probe-appcontainer-peer-controls.txt` | 同 profile LOCAL 收发及负对照已观察；非实际插件证明 |
| 源不透明资源剪切/粘贴保护及正常扩展剪切 | `artifacts/feature-acceptance-adac1d5901d0/summary.json` | 3 通过，含清理 |
| AI 扩展剪切、粘贴、合并、旧历史与普通兼容 | `artifacts/feature-acceptance-e57fec059ac3/summary.json` | 7 通过，含清理 |
| 轨道、片段、音符扩展剪切 | `artifacts/feature-acceptance-4cb5b47a3915/summary.json` | 2 通过，含清理 |
| 根/主轨扩展及目标额外资源保留 | `artifacts/feature-acceptance-288f3f9a90b8/summary.json` | 2 通过，含清理 |
| AI 剪贴板扩展迁移、偏移、旧历史及源保护 | `artifacts/feature-acceptance-b8c01e2d4375/summary.json` | 3 通过，含清理 |
| 扩展拆合、冲突回滚、剪贴板源保护和 MIDI 事件流 | `artifacts/feature-acceptance-a4a1a5dc7d8d/summary.json` | 5 通过，含清理 |
| MIDI 错误、积压通知与提交前检查 | `artifacts/midi-callback-b0fae6312bd4.json` | 逻辑测试通过，未打开 MIDI 设备 |
| 默认 AI 轨道、显式选声、编辑保存重开及合成 | `artifacts/feature-acceptance-32f1c9da5151/summary.json` | 2 通过，含清理 |
| 扩展字段的轨道/片段/音符复制、历史及歧义保护 | `artifacts/feature-acceptance-647c107fc2bd/preservation.duplicates.json` | 通过；同次 MIDI 枚举旧失败保留 |
| MIDI 六操作、录制状态与保存重开 | `artifacts/feature-acceptance-878d0c135692/summary.json` | 2 通过，含清理；无硬件输入 |
| MIDI 事件流、跨速度变化和静音同步 | `artifacts/midi-synthetic-3fa675486b20.json` | 通过；枚举两端口但未打开 |
| 正式冻结 MCP、设备传输、119 项目录 | `artifacts/feature-acceptance-26a71f9b1dc5/summary.json` | 4 通过，含清理 |
| 五级未知字段、三类资源与实体历史 | `artifacts/feature-acceptance-d58315058dcd/summary.json` | 3 通过，含清理 |
| 固定嵌套对象、转义键、已知值修改 | `artifacts/feature-acceptance-1fc72536a94a/summary.json` | 2 通过，含清理 |
| 带扩展的速度、调音、循环、批量音符及表现修改 | `artifacts/feature-acceptance-f0e3121b86c8/summary.json` | 2 通过，含清理 |
| 原有音频资源、克隆恢复、特殊音素 | `artifacts/feature-acceptance-e45608aa7004/summary.json` | 4 通过，含清理 |
| 非零起点、多片段、效果和自动化冻结音频 | `artifacts/freeze-chain-6ad650a432ef.json` | 18 秒混音；差异 RMS 约 0.00001272，作者 JSON 不变 |
| 冻结正式入口、失败清理和源保护 | `artifacts/freeze-mcp-59c5a9b898b7.json` | 通过 |
| 内部采样率的版本限定静态证据 | `artifacts/internal-rate-static-aa7e6f0f7992.json` | 找到 44100 比较与对应错误码；不等于 96 kHz 动态验证 |

0.2.1 的真实 PPSF3（190 音符、80 BPM、4/4）及显式选声后的 99.5 秒非零 WAV、Robot 和其他表现证据见 [会话 07](docs/session-log/session-07.md)。其长音频旧 case 的 30 秒读取上限失败记录仍保留，独立流式检查通过，不重写历史结果。

## 保留边界

1. **声库选择**：用户明确仅用 AI 声库，不安装经典试用。此前本机 Dse=0、Dnn=21；旧经典文件继续受到源文件与身份完整性保护，经典发声和往返不作为本轮 AI 声库的验收结论。
2. **未知数据**：除速度和拍号事件外的非实体数组、拍号扩展合并、缺失父对象及纯元数据合并、原生音频资源迁移，以及部分原始写调用仍受保护性限制；受测不透明资源按工程级迁移，不等于原生音频资源归属。扩展剪贴板和工程合并使用独立候选预检；其他编辑路径仍可能在保存时发现同形歧义，详见 [工程保留说明](docs/project-preservation.md)。没有把此范围称作任意 VPR 无损编辑。
3. **设备与宿主**：传输验证使用一台 DirectSound 设备并静音；虚拟 MIDI 驱动的独立输入已验，物理 MIDI 采集、真实设备丢失及驱动错误通知、实际听音质量和 DAW 同步仍未完成验收。插件已观察到固定命名管道路径，[IPC 隔离调查](docs/daw-ipc.md) 尚未证明独立宿主隔离；编辑器不具备波形录音功能，见 [音频录制与宿主边界](docs/audio-recording.md)。
4. **采样率**：声乐内部合成明确要求 44100 Hz；输出混缩率独立。静态分支与 48 kHz 失败一致，但其他原生内部路径与 96 kHz 动态合成未证实。
5. **客户端**：新 stdio 连接已验证本轮原生改动；本对话连接此前发现 37 个工具，但 `vocaloid_status` 的 Python MCP 版本为 0.4.0，运行中的原生宿主此前与 0.5.0 构建一致；0.8.0 原生改动需新连接载入。未重启客户端或用户编辑器。

当前模块状态见 [功能矩阵](docs/feature-matrix.md)、[会话 13](docs/session-log/session-13.md) 和 [TODO](TODO.md)。
