# 会话 36：客户端绑定确认与 Agent 作曲流程

日期：2026-11-10。起点提交：`9626ced39c17b1c77ae015ae835c0176a9572250`。前半确认 0.26.0 的客户端绑定，提交为 `716cf31`；后半完成 0.27.0。

## 第一部分：客户端绑定确认

用户要求查看项目并完成剩余 TODO；简单任务可分派给 Haiku 子 agent。TODO 只剩一项：客户端重新建立 MCP 工具绑定后确认 0.26.0，只查一次状态，不重跑功能测试。本会话是新建的 Claude Code 聊天（桌面应用 Code 页，Claude Code 2.1.317），拥有自己的 `vocaloid6-native` 服务进程，其启动命令与用户级 `.claude.json` 的条目一致。它不是原 Codex 聊天的旧传输。

- 客户端工具列表含 38 个 `vocaloid6-native` 工具，包括 0.26.0 新增的 `vocaloid_runtime`。
- 单次 `vocaloid_status`：`mcp_version=0.26.0`、`backend=native-vsm`、原生引擎 6.13.3.1、0 会话、代次 1、`fallbacks=false`，实际 desktop 与 `isolation_desktop_expected` 相同。
- 该调用按设计拉起私有原生实例，随后用 `vocaloid_runtime stop` 结束，`discarded_sessions=0`。停止后原生进程已退出，缓存命名空间在 VSM 与 VSMCaches 下均不存在，`.runtime/tmp` 和 `.runtime/mcp-temp` 为空，运行副本目录没有新增，`output` 没有新文件。
- 静态核对：`server.py` 38 个工具，`operations.json` 127 个操作，`generate_operation_catalog.py --check` 通过；原生构建时间晚于全部 C# 源文件。

回执：`artifacts/mcp-binding-confirmed-36.json`。这一部分没有重跑功能测试、修改代码或重建原生宿主。原 Codex 聊天的旧绑定没有重试，不称为已恢复。同一桌面应用中另一个 Claude Code 进程持有独立的服务进程，未触碰。

## 第二部分：0.27.0

### 用户要求

用户问功能矩阵中 P-13（非 44100 Hz 内部合成）和 L-08（其余 Attack/Release 组合）是什么、是否影响做歌，并要求：做歌需要的功能都要做好，Agent 要能正常调用应该能调用的功能。

### 调查

- 经这个聊天自己的 MCP 连接实际做了一遍：新建工程、AI 轨、声部、指定声库、加音符、渲染、改表现参数、48/96 kHz 混缩、素材捕获和导入。
- 让一个 Haiku 子 agent 只凭 MCP 自身的说明做一段 8 个音的中文演唱，不许读仓库文件。它用 42 次调用完成，并如实列出每个障碍，见 `artifacts/agent-trial-haiku-36.json`。
- 写了 `tools/check_ai_effect_audit_36.py`：同一段 asa 短语每次从保存的工程重新打开、施加一项控制后渲染，与基线逐样本比较。基线两次渲染逐样本相同。

### 结论

- P-13 不影响做歌：手册第 37 页写明内部运行规格为 44.1 kHz，交付采样率在混缩时选择。
- L-08 不影响 AI 做歌：Attack/Release 属于标准 VOCALOID 声部，AI 音符上设置后渲染结果逐样本相同。
- 88 项比较中 34 项改变 AI 合成、53 项不改变、1 项被拒绝，与手册的 AI 参数表一致。AI 实际演唱的是：音高与歌词、10 个 `ai_expression` 音高/音量字段、`pitch.set`、Dynamics/PitchBend/Expression/S5Air/S5Character 曲线、带 depth 事件的颤音、取消旁路后的三项 S5 VoiceColor，以及此前已有音频证据的 Breath、Take、Robot 和音素时序。
- 审计自身的对照项先失败了一次：`note.update` 只改 `lyric` 时文字变了，音素和声音不变。这是一个会让 Agent 改词不改音的实际问题。

### 修改

- 原生：AI 音符的 `note.update` 在 `lyric` 或 `lyric` 加 `lang_id` 变化且未给音素时重新生成音素，复用新音符的单音节转换和校验，拒绝时回滚；受保护音符、显式音素和标准声部保持原行为。歌词被拒绝的报错按语言给出写法。`voice.get/set` 附 `installed_voice`，`controller.types` 和 `dvqm_get` 标注适用声部，`vibrato.get` 返回类型名和取值范围。
- Python：新增 `vocaloid_workflow`，服务说明和各工具说明写入 tick 精度、歌词写法、44100 Hz 工程、默认样式和干声渲染的含义；`vocaloid_operations` 不带范围索取全部文档时报错；`score_compose` 的歌词拒绝信息给出写法。版本 0.27.0，39 个工具。
- 文档：新增 `docs/song-workflow.md`；更新乐谱、素材库、音频操作契约并重建操作目录；功能矩阵按审计结果改写相关行，P-13 改为 V，新增 U-10。

### 验证

`artifacts/agent-song-36-evidence.json` 索引全部回执。审计 `ca89e374bac1` 通过；四项新用例 `ee0bdfc0c02a` 通过；受改动影响的 19 项既有用例重跑通过，包括 `score.note_add_31`、`library.lyrics_transactions_31`、两项 compose/replace 音素用例和两项 0.26.0 生命周期用例。原生语义预检 32 文件 / 211 引用零错误，Release 构建零警告零错误。没有运行全量套件。

21 批运行中 3 批失败，回执保留：审计对照项选错（`aee918ba828f`）、用例对日语多音节歌词的预期写错（`27f564e7f748`）、同一调用解除保护并改词时原生音符拒绝写入音素（`f05491c77ab9`，已改为先解除保护）。

### 未完成与边界

- 这个聊天的服务进程仍是 0.26.0。客户端重新连接后才载入 0.27.0，已列入 TODO；届时只查一次状态。
- 审计只用了 asa，其他 20 个 AI 声库没有逐个比较；它衡量控制是否改变合成，不评价音质。Haiku 做出的音频没有人听过。
- 功能矩阵还有 7 个 I 行，都卡在经典声库、物理 MIDI、实际听音或用户全局设置上。`.github/copilot-instructions.md` 的“完整编辑器功能覆盖已验证”保持未勾选。
- 实例正常停止后仍留下一个空的 stderr 日志，没有改。
- 除 Haiku 试做外没有分派其他子 agent。

## 清理

第一部分删除 1 个空的 stderr 日志（`artifacts/cleanup-36.json`）。第二部分删除 73 个自有文件，共 7,325,447 字节：测试生成的 VPR/WAV、空的 stderr 日志和构建临时文件（`artifacts/cleanup-36b.json`）。Haiku 的三个输出文件保留在 `output/haiku36-*`。私有进程临时目录和 MCP 临时目录为空。更早遗留的 430 个 stderr 日志（18 个非空）和 8 个运行副本目录归属未确认，保持原样。
