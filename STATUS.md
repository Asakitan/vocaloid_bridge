# 当前状态

日期：2026-11-10。版本：0.2.1。目标继续进行；尚未完成所有功能与环境组合的验收。

## 已实现与实测

- 36 个 MCP 工具，65 个乐谱、9 个音频、30 个素材、5 个剪贴板操作，共 109 个；新增 `note.expression_bounds` 返回原生表现字段范围和默认值。
- 保留原生创建、打开、编辑、保存、关闭、克隆和恢复；所有原生宿主运行在私有 Windows desktop，源工程与独立输出分离。
- Robot 的同会话编辑后声音不变已修复：保留每宿主独立缓存命名空间，并将原生渲染缓存容量设为零；等待目标片段完成事件或序列完成状态，再发布实际 WAV。原失败用例及同宿主双会话音频完整性通过。
- 真实公开 PPSF 3.2 `Monologue.ppsf` 的 1 条 NT 轨、190 个音符完成原生导入、VPR 保存与重开；源文件未变。作者样本仅保存在被忽略的运行目录，未收入源码。
- 该样本显式选择本机 `asa` 后，声库身份保存重开并产出 99.5 秒非零原生音频；独立流式复核通过。原验收用例因通用读取器的 30 秒上限失败，保留原失败记录，没有重渲伪造成功用例。
- 19 个音符表现字段、9 个 VoiceColor 字段与 Take 车道有参数读写、素材捕获和保存重开证据；VoiceColor 返回当前轨道适用性。三项 AI VoiceColor、Take、Breath 启用/频率/音量有实际 PCM 差异；经典字段与 Breath 类型的声音边界单独记录。
- `OpenSequence` 使用已安装程序集目录作为 `vsqxSchemaDirPath`。新增 `ProjectIntegrity.cs`：检查轨道类型、片段数量和非空声库身份；原生保存若丢失身份则在发布前报错，已有输出不被替换。
- 44.1 kHz 内部合成在 bus 0/1 下分别输出 44.1/48/96 kHz 均非零。输出采样率与工程内部合成率分离；内部 48/96 kHz 的声乐渲染现明确快速报错，工程参数仍可读写。

## 当前边界

1. **经典声库依赖**：本机枚举到 Dse=0、Dnn=21；已定位的 VSM 数据库计数分支与经典轨道载入为 AI 的实测一致，另有保存时缺失经典身份的问题。打开前报 `missing_classic_bank`，保存/克隆丢失身份时报 `project_integrity`。保护行为已验，不算经典发声或经典无损往返通过。用户选择暂不安装试用声库。
2. **音频路由**：离线混缩按所选轨道求和；`bus_no` 是外部宿主输出映射，离线文件不代表真实 DAW 总线验收。48 kHz 内部 DSE 曾返回 `FailedToCreateDseWaveBuffer`；96 kHz 内部 DSE 未直接验证。
3. **外部环境**：设备播放、实时输入/录制、DAW 同步仍需对应环境；用户编辑器窗口、全局偏好和授权不在操作面。
4. **客户端发现**：新建真实 stdio 连接发现 36 工具；已有客户端应重载 `vocaloid6-native` 后使用新增操作目录。没有重启用户客户端或编辑器。

## 验证证据

构建：0 警告、0 错误。仅对具体改动进行定向验证；历史整合回执不冒充当前完整通过。

| 范围 | 回执 | 结果 |
| --- | --- | --- |
| 本轮生命周期、真实 PPSF3、双 AI 声库、特殊音素 | `artifacts/feature-acceptance-983dee33baea/summary.json` | 6 通过，含清理 |
| 经典完整性保护、正常 AI 往返 | `artifacts/feature-acceptance-8a94a4ae3dcd/summary.json` | 3 通过，含清理；不是经典合成通过 |
| 不依赖历史输出的完整性回归、当前操作目录 | `artifacts/feature-acceptance-2ccd799e0d5e/summary.json` | 3 通过，含清理 |
| 完整表现参数与 VPR 导入 | `artifacts/feature-acceptance-9eec19449679/summary.json` | 4 通过，含清理；旧运行器选择标记问题已修正 |
| VoiceColor 适用性及参数素材往返 | `artifacts/feature-acceptance-bf40360385c5/summary.json` | 2 通过，含清理 |
| Robot 原失败回归 | `artifacts/feature-acceptance-b08ff3a55109/summary.json` | 声音差异、保存重开和混缩通过 |
| Robot 同宿主双会话 | `artifacts/robot-concurrent-55f6b5ff5c73.json` | 另一会话的音频 PCM 保持一致 |
| 三项 AI VoiceColor 和旁路声音 | `artifacts/feature-acceptance-dc7fdcb678e4/voicecolor.audio.json` | 测量及清理通过；旧运行器误选全量覆盖而非零退出，选择逻辑已修正 |
| Take 两车道声音、参数往返 | `artifacts/score-parameters-66761d50d26c.json` | 独立创建夹具，差异 RMS 约 0.01557 |
| Breath 声音与参数往返 | `artifacts/feature-acceptance-f01a08f3680e/summary.json` | 2 通过；Male/Female 在此 AI 样本声音相同 |
| PPSF3 源事件与速度/拍号 | `artifacts/feature-acceptance-a3cc87f45ce7/summary.json` | 190 音符位置、时值、音高、歌词及 80 BPM、4/4 通过 |
| PPSF3 显式选声后的原生音频 | `artifacts/ppsf3-render-stream-check-9ec33f2e51bf.json` | 4,387,954 帧、RMS 0.03772；原 case 的检查器超限失败记录保留 |
| 输出采样率与总线组合 | `artifacts/audio-routing-acda7649870c.json` | 6 个非零混缩通过；不代表 DAW 路由 |
| 内部采样率保护 | `artifacts/audio-routing-guard-9f833b494596.json` | 参数读写和快速错误通过 |
| 经典载入分支 | `artifacts/classic-native-audit-025cb925c173.json` | 版本限定的静态证据，附历史原生声库计数 |

上轮整合 `artifacts/feature-acceptance-012574702338/summary.json` 为 76 通过、5 失败、2 个缺样本项；Robot 与 PPSF3 已有上述更新，经典项保留依赖边界。历史、模块细节及下一步见 [会话 07](docs/session-log/session-07.md)、[功能矩阵](docs/feature-matrix.md) 和 [TODO](TODO.md)。
