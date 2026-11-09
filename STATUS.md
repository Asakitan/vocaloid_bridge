# 当前状态

日期：2026-11-10。版本：0.3.0。完整目标继续进行，不把受测范围扩大为所有输入与环境组合。

## 当前入口与实测

- 36 个 MCP 工具，68 个乐谱、16 个音频、30 个素材、5 个剪贴板操作，共 119 个。创建、打开、编辑、保存、关闭、克隆和恢复保留。
- 新增 `devices` 与 `transport_prepare/status/play/stop/seek/release`：明确选择设备，原生 VAE 独立播放；不改系统默认设备或用户编辑器。DirectSound 静音时钟、停止、异步定位、释放后保存、关闭自动释放通过。
- 新增 `track.freeze/freeze_state/unfreeze`：只持有会话自有缓存；修正预送时基、多片段范围和重复音量/声像处理。保存与克隆写出原始作者状态，冻结缓存不持久化。多片段、非零起点、Gain 和音量自动化的受测混音差异约 0.054%。
- 修复原生保存/克隆丢弃未知工程数据：保留 root/master/track/part/note 未知字段、固定嵌套对象字段，以及额外 ZIP 资源；仅覆盖未知键，不恢复旧的已知值。原生实体通知和真实历史边界防止删除重建时元数据错贴。
- 未知数据覆盖包括已验证的重排、更名、音符移动/修改、删除同值新建、撤销/重做、参数编辑、保存重开，以及源关闭后的克隆。非实体数组和复杂复制语义仍有明确限制。
- 0.2.1 的 Robot 零结果缓存修复、19 个音符表现字段、VoiceColor 适用性、Take/Breath/AI VoiceColor 声音证据和真实 PPSF3 样本继续保留。

## 本轮证据

构建：0 警告、0 错误。只运行改动相关检查，未重跑完整历史套件。

| 范围 | 回执 | 结果 |
| --- | --- | --- |
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

1. **经典资源**：此前本机 Dse=0、Dnn=21，经典身份和效果的完整验收仍依赖对应声库。此前暂缓试用安装；本轮对是否启动 14 天计时再次确认，尚未开始安装。
2. **未知数据**：带实体扩展的重复签名、非实体数组内扩展、split/join、复制粘贴、合并及部分原始写调用仍受保护性限制，详见 [工程保留说明](docs/project-preservation.md)。没有把此范围称作任意 VPR 无损编辑。
3. **设备与宿主**：传输验证使用一台 DirectSound 设备并静音；实际听音质量、实时输入录制和 DAW 同步仍未完成验收。
4. **采样率**：声乐内部合成明确要求 44100 Hz；输出混缩率独立。静态分支与 48 kHz 失败一致，但其他原生内部路径与 96 kHz 动态合成未证实。
5. **客户端**：新 stdio 连接已验证新增操作；既有客户端需要重载 `vocaloid6-native`。本轮未重启客户端或用户编辑器。

当前模块状态见 [功能矩阵](docs/feature-matrix.md)、[会话 08](docs/session-log/session-08.md) 和 [TODO](TODO.md)。
