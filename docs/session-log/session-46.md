# Session 46: V7 参数入口与工程保护

日期：2026-11-11。

## 目标

修复可复现的正常编辑误拦截，保留未知字段和资源的身份保护。对照用户的 V7 截图补齐 AI 可发现、可写入、可读回的参数；界面布局与工程数据分别说明。

## 基线

- 保留会话 45 未提交的 batch.run 分发与子操作检查修改。
- 已有 V7 track scope、VoiceType、performance、style 和曲线入口；当前功能矩阵仍包含 V6 历史证据，不能直接计为 V7 验收。
- 当前聊天未暴露 VOCALOID MCP 工具，集成验收使用仓库既有真实 stdio MCP 流程，不修改注册配置或用户交互编辑器。

## 验证范围

以自建 GekiyakuV 三音短句及带未知字段的工作副本核对参数读写、撤销、保存重开、资源保留与非静音合成，未修改用户 DemoSong。

## 修改

- `ProjectArchivePreservation.cs` 将 V7 主/副声库 compID 加入轨道身份指纹，并与原生 ID 核对。原先同形但不同声库的轨道会误报身份歧义；同 ID 且未知字段冲突仍拒绝。没有放宽 `ProjectIntegrity.cs` 的结构、声库表与身份检查。
- `ScoreOperations.cs` 增加 VoiceType 选择及真实列表、Attack 的 V7 声库限制、合成音高保留和 AI 默认颤音恢复。Robot 使用原生效果 setter；轨道便利方法会调用 `App.SequenceManager`，不适用于私有后台宿主。
- `V7AiOperations.cs` 新增 `ai.status/generate`。生成调用既有原生渲染器，使用临时 WAV 检查文件后删除，不交付假音频。`preserve_pitch=true` 以一次音高事务固化所选音符，默认拒绝覆盖已有点；曲线提交可能使当前缓存需要重新生成，`render_observation` 与当前 `status` 分别报告。
- `server.py` 增加 `project_inspect` 和 `project_ai_adjust`，功能导航共 39 项（V7，含不支持项），41 工具/130 操作。AI 包装层预检失败时不先改 Take；Take 改动后生成失败会报告已完成的整轨修改，不重放。

## 验证结果

- V6/V7 语义预检各 35 文件、218 引用、零错误；V7 Release 构建通过，V6 本轮未构建。
- `tools/check_v7_integrity_offline.py`：旧程序集复现误报，修后 7 项身份正负例通过，不启动宿主。
- `tools/check_v7_controls_46.py --case v7.controls_46`：真实 stdio MCP 用例及清理 2 项通过，回执 `artifacts/feature-acceptance-78bc268d0a70/summary.json`。
- GekiyakuV Normal/Power 真实列表及切换、默认 Style（4 MIDI 效果/5 音频效果）、四类 Voice Color、Robot/Breath/Exhalation、batch 编辑、参数撤销/重做、只读功能检查均通过。
- 原生 AI 生成完成且 score/wave 有效；AI 默认颤音恢复为 `AiEstimatedBase`。两个音符分别保留 129/190 点，一次 undo 清除、redo 恢复；默认覆盖拒绝保持曲线，VPR 保存重开仍相同。
- root/track/part/note/voice/MIDI effect/参数未知字段及额外 ZIP 资源保留，原输入字节不变。重开后 WAV 为 342877 帧、44100 Hz mono PCM16、7.774988662 秒、peak 0.1215209961、RMS 0.0152129538。
- 最终零会话，无自有进程抢占前台。后续仅补功能导航，离线确认所有模板映射到已登记操作、V6/V7 作用域及开关语义，未再次合成。

## 已修复的验收失败

1. `feature-acceptance-b2208843189c`：夹具给模板传入未在其 voices 表中的声库。改为原生 `voice.set` 后继续。
2. `feature-acceptance-7e4ad99025af`：V7 Robot 轨道 setter 触发 `Yamaha.VOCALOID.App` 静态初始化。只读核对安装程序集后改为原生效果 setter，保留私有脚本管理。
3. `feature-acceptance-c07db521cce4`：Python 从 `ai.status` 外层回执读取 notes，改为 `result.notes`。

离线整合另修正未保留音高时传入 `overwrite_existing=false` 的参数存在性冲突。没有把早期失败记录改成通过。

## 边界与交付

本轮未重跑全量 V7 套件、全部参数声音差异、设备/DAW 或主观听音；未证明任意扩展组合均可编辑。纯 UI 网格、缩放、面板和角色图不操作；V7 VMM、片段音频效果、反转/变声继续明确不支持。

本轮发布为 0.30.0，已提交并推送至 `master`。当前聊天未暴露 VOCALOID 工具，以上是实际独立 stdio 证据。客户端需保存关闭工程并重连，检查 0.30.0、41 工具及 `project_ai_adjust`。