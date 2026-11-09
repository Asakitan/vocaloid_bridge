# 当前状态

日期：2026-11-10。版本：0.5.0。完整目标继续进行，不把受测范围扩大为所有输入与环境组合。

会话 09：用户明确选择仅使用 VOCALOID:AI 声库；不安装经典声库试用，继续扩展 AI 工程编辑及后台设备能力。
未指定类型的 `track.create` 默认改为 `MidiAi`；空工程到显式选声、编辑、保存重开和合成的定向验证见 `artifacts/feature-acceptance-32f1c9da5151/summary.json`。显式 `Midi` 类型及旧工程保护保留。

会话 10：带未知实体字段的音符及片段拆合、冲突回滚和历史有定向 MCP 验证；AI 剪贴板剪切/迁移、工程合并及旧历史、MIDI 错误回调的定向检查通过。DAW 固定命名管道隔离和真实 MIDI 硬件仍待验证。

## 当前入口与实测

- 37 个 MCP 工具，68 个乐谱、16 个音频、30 个素材、5 个剪贴板和 6 个 MIDI 录制操作，共 125 个。创建、打开、编辑、保存、关闭、克隆和恢复保留。
- `project_midi` 提供设备枚举、显式设备或事件流录制、状态、停止和取消；事件流的音符、速度映射、保存重开与静音 transport 同步已验。输入错误通知、回调故障和溢出阻止提交；逻辑测试未打开真实 MIDI 输入。
- 新增 `devices` 与 `transport_prepare/status/play/stop/seek/release`：明确选择设备，原生 VAE 独立播放；不改系统默认设备或用户编辑器。DirectSound 静音时钟、停止、异步定位、释放后保存、关闭自动释放通过。
- 新增 `track.freeze/freeze_state/unfreeze`：只持有会话自有缓存；修正预送时基、多片段范围和重复音量/声像处理。保存与克隆写出原始作者状态，冻结缓存不持久化。多片段、非零起点、Gain 和音量自动化的受测混音差异约 0.054%。
- 修复原生保存/克隆丢弃未知工程数据：保留 root/master/track/part/note 未知字段、固定嵌套对象字段，以及额外 ZIP 资源；仅覆盖未知键，不恢复旧的已知值。原生实体通知和真实历史边界防止删除重建时元数据错贴。
- 未知数据覆盖包括已验证的重排、更名、音符移动/修改、轨道/片段/音符复制和 AI 剪贴板剪切/跨工程粘贴、AI 工程合并、音符及片段拆合、删除同值新建、撤销/重做、参数编辑、保存重开，以及源关闭后的克隆。非实体数组和额外资源的跨工程迁移仍有明确限制。
- 0.2.1 的 Robot 零结果缓存修复、19 个音符表现字段、VoiceColor 适用性、Take/Breath/AI VoiceColor 声音证据和真实 PPSF3 样本继续保留。

## 本轮证据

构建：0 警告、0 错误。只运行改动相关检查，未重跑完整历史套件。

| 范围 | 回执 | 结果 |
| --- | --- | --- |
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
2. **未知数据**：非实体数组内扩展、源工程 root/master 未知字段和额外资源跨工程迁移，以及部分原始写调用仍受保护性限制；拆合、剪切、粘贴和合并仅通过受测语义的映射，同形轨道若数据不一致也会拒绝，详见 [工程保留说明](docs/project-preservation.md)。没有把此范围称作任意 VPR 无损编辑。
3. **设备与宿主**：传输验证使用一台 DirectSound 设备并静音；实时 MIDI 硬件采集、驱动通知、实际听音质量和 DAW 同步仍未完成验收。插件已观察到固定命名管道路径，[IPC 隔离调查](docs/daw-ipc.md) 尚未证明独立宿主隔离；编辑器不具备波形录音功能，见 [音频录制与宿主边界](docs/audio-recording.md)。
4. **采样率**：声乐内部合成明确要求 44100 Hz；输出混缩率独立。静态分支与 48 kHz 失败一致，但其他原生内部路径与 96 kHz 动态合成未证实。
5. **客户端**：新 stdio 连接已验证 0.5.0 的定向操作；本对话连接从先前的 `Transport closed` 恢复，当前发现 37 个工具，但 `vocaloid_status` 的 MCP 版本仍为 0.4.0。重新连接 `vocaloid6-native` 后应核对版本；未重启客户端或用户编辑器。

当前模块状态见 [功能矩阵](docs/feature-matrix.md)、[会话 10](docs/session-log/session-10.md) 和 [TODO](TODO.md)。
