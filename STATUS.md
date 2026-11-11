# 当前状态

日期：2026-11-11。版本：0.30.0。41 个工具、130 个结构化操作；V7 功能导航为 39 项（含明确不支持项），不等于全量验收。

## 0.30.0：V7 工程保护与 AI 调整

- 修复 V7 轨道主/副声库未纳入归档指纹造成的同形轨道误拒绝；真实身份冲突及声库表缺失仍拒绝，未知字段不清空。
- 新增 `project_inspect`，按截图功能读取实际参数、枚举与范围；`vocaloid_features` 区分 V6 历史证据和 V7 调用契约。Voice Type 可选择，Attack 按声库代际校验，Robot 模式修改不再调用交互编辑器的 `App.SequenceManager`。
- 新增 `project_ai_adjust` 与 `ai.status/generate`：使用原生 VOCALOID:AI 生成演唱数据，可选择 Take 和将生成音高保留为可编辑曲线；默认不覆盖已有曲线。支持原生 AI 默认颤音恢复，多个音符保留为一次可撤销事务。生成不是独立审美优化，也不自动保存 VPR 或导出交付 WAV。
- 验证：V6/V7 语义预检各 35 文件、218 引用、零错误；V7 Release 构建通过。修后身份保护 7 项正负例通过；真实 stdio GekiyakuV 的 Style、Voice Type、参数、batch、AI 生成、双音符固化、撤销/重做、防覆盖、未知字段与资源保留、保存重开及非静音渲染通过。固化点数 129/190，WAV 342877 帧、peak 0.1215209961、RMS 0.0152129538。

证据：`artifacts/feature-acceptance-78bc268d0a70/summary.json`；该运行 2 项通过（功能用例及清理），结束后零会话、无自有进程抢占前台。早期夹具声库选择错误、Robot App 依赖和 Python 回执解析失败均已修复，原回执保留，见 [会话 46](docs/session-log/session-46.md)。当前聊天未暴露 VOCALOID MCP 工具；保存关闭工程后重新连接 `vocaloid6-native`，看到 41 工具及 `project_ai_adjust` 才表示客户端载入了本轮代码。未重跑全量套件、V6 构建或主观听音。

## 0.30.0：batch.run 归档保护修复

带扩展的工程此前在外层把 `batch.run` 当作未知 mutation 直接拒绝。现允许 batch 分发，但每个子操作仍在执行前进入 `CheckArchiveRequest`；嵌套 batch 仍拒绝，首个失败前已完成的操作不会自动回滚。V7 语义预检 34 文件 / 218 引用 / 零错误，V7 构建通过；实际 stdio 七音工程的 batch 正例、嵌套 batch 负例、保存重开与非静音渲染通过，回执位于 `E:/VC/LabyRinth/production/vocal/gkv7/native_probe_75ef6c62a9.json`。后续五段 GekiyakuV 994 个音节的保存、重开与渲染通过；未重跑全量扩展组合或 V6 构建。详见 [会话 45](docs/session-log/session-45.md)。

## VOCALOID7 与自动选择（0.29.0）

安装选择器读取注册表、标准安装目录和实际核心 DLL 版本；本机默认选中 VOCALOID7 7.0.0.1，显式 `VOCALOID_INSTALL` 可固定 V6。每个新宿主重新选择，活动宿主固定版本。V6/V7 使用隔离的 .NET 10 构建目录与严格目标标记，缺少匹配产物时报错并提示重建，不启动旧 DLL 或静默降级。MCP 注册名未改。

V7 使用轨道级声库、样式及表现参数，要求 `scope="track"`；颤音使用 `curve_model`，Take 使用 `take_number`。打开、克隆和导入时，为缺少 `VoiceTypeID` 的 AI 轨补同一声库的原厂默认类型，并返回 `initialized_voice_types`；不替换声库或已有类型。渲染前拒绝无效类型。文件级编曲识别 V7 轨道 `voice`，不再依赖旧片段 `aiVoice`。

本次阻塞来自把 V6 API 直接套到 V7、构建失败后仍运行旧 DLL、迁移工程缺少 `VoiceTypeID`，以及取消后可能复用失步连接。已删除未奏效的渲染初始化猜测，构建失败即停止，取消关闭自有连接且不重放。详见 [会话 44](docs/session-log/session-44.md)。

| 验证 | 结果 |
| --- | --- |
| V6/V7 原生语义预检与独立 Release 构建 | 各 34 文件 / 218 引用 / 零错误；两个产品均构建成功 |
| 自动选 V7 的真实 stdio MCP 编曲、自动音素、保存重开、合成 | 374850 帧 / 8.5 秒，peak 0.1131896973、RMS 0.0134845327；回执 `artifacts/background-demo-b575e1fb9f.json` |
| 显式 V6 的同一流程 | 374849 帧，peak 0.1177368164、RMS 0.0138640943；回执 `artifacts/background-demo-603fccdd6a.json` |
| V7 原生 asa、纯 V7 文件替换音符和自动音素、重开 | 声库 ID、默认类型和音符读回通过，回执 `artifacts/v7-native-roundtrip-05554c8b.json`；本项未渲染 |
| 最终独立 stdio 状态 | MCP 0.29.0、VOCALOID7 7.0.0.1、39 工具、零会话、轨道作用域；`artifacts/v7-final-status-44.json` |
| 缺省类型根因探针 | 同一个旧 asa 补类型后渲染成功；`artifacts/v7-voice-type-probe.json` |

两次 stdio 合成结束后会话数均为 0，前台窗口保持不变。安装选择器的 6 项定向检查、取消连接失效检查和 V6/V7 文件音符身份检查通过。没有重跑全量功能套件。V7 的 VMM 素材操作、片段音频效果、WOR 反转和变声明确拒绝；V7 混缩、复杂扩展迁移及全部参数声音差异未逐项验收。当前聊天未暴露 VOCALOID MCP 工具，以上是独立真实 stdio 与原生客户端证据，不是当前聊天已重连的证明。

## 临时文件自动清理（0.28.0）

`vocaloid_bridge/cleanup.py` 在 MCP 服务启动时后台扫描，之后每 10 分钟重复一次。清理范围是 `output/` 下修改时间超过 1 小时的文件、`.runtime/mcp-temp` 的旧临时文件、已退出宿主的 `.runtime/tmp/VocaloidBridge-*` 目录及同名 `.stderr.log`。仍在使用的文件、reparse point 和 `.runtime` 的其他内容（手册、素材库、宿主副本、探针、日志以外的记录）保持不动。删除清单写入 `.runtime/temp-cleanup/last-report.json`，`vocaloid_status.temp_cleanup` 返回最近一次结果。`VOCALOID_TEMP_CLEANUP=0` 关闭自动清理；`VOCALOID_TEMP_MAX_AGE_SECONDS` 和 `VOCALOID_TEMP_CLEANUP_INTERVAL_SECONDS` 调整年龄与周期，默认 3600 秒和 600 秒。

`tools/clean_temp_output.py` 是手动入口：默认 dry-run，只打印候选；`--apply` 才删除；`--keep GLOB` 按相对路径或文件名保留匹配项。首次实际清理删除 4573 个文件、5 个空目录、5,503,881,176 字节，保留 14 个一小时内的渲染/临时项，失败 0；清理后 `output/` 只剩最近一小时内生成的 13 个文件。独立假工作区自测覆盖新旧文件、嵌套目录、keep、活动宿主日志和 dry-run 不落盘；服务导入后的 `vocaloid_status.temp_cleanup` 返回同一回执。本次没有重跑全量功能套件。

## 整曲制作中的补充实测（会话 42）

只补文档，没有改代码、重建宿主或重跑验收：零间隙大跳进会被引擎滑成警笛式扫频，把到达音符的 `PitchTransitionStart`/`PitchDriftStart` 和离开音符的 `PitchTransitionEnd`/`PitchDriftEnd` 压低（0.0–0.1 / 0）可以消除；句末 Dynamics 在音符结束处回升会让元音收音冒出爆音；`note.batch_update` 只带 `lyrics` 不重新生成音素；take 批处理会覆盖手改的 PitchBend。细节与未验证项见 [session-42](docs/session-log/session-42.md)。

## README 猫娘化与更新日志拆分（会话 41）

`README.md` 改成猫娘助手口吻，保留安装、39 工具表、后台约束和验证入口；命令、参数、路径与表格值不加语气词。已安装客户端表、E 盘启动参数、连接/版本状态、本机声库计数、输出与清理记录移到 `.vscode/handoff/local-environment.md`，该目录已被忽略，不进入公开仓库。验证示例改用 `<MANUAL_TEXT>`、`<VSQX>`、`<PSSF>` 等占位符。

新增根目录 `CHANGELOG.md`，按 Keep a Changelog 记录 0.1.0–0.27.0 的版本变化；README 正文不再写版本号和单次会话记录，只链接更新日志、STATUS 和会话索引。

本次只改文档，没有改代码、重建宿主或重跑验收。README 保留 39 工具/127 操作的当前能力数字。

## 公开仓库与许可证（会话 40）

源码以 MIT 许可证发布：根目录 `LICENSE` 版权署名为 Asakitan（2026），`pyproject.toml` 的 `project.license` 引用该文件，README 说明桥接代码与 VOCALOID 第三方组件的授权范围区别。公开仓库为 [Asakitan/vocaloid_bridge](https://github.com/Asakitan/vocaloid_bridge)，`origin` 使用 HTTPS，默认分支 `master`。

发布前核对了 401 个候选文件：无 `.env`、访问令牌、私钥或证书；`output/`、`artifacts/`、`.runtime/`、`.venv/`、`native/bin|obj/`、`.vscode/handoff/` 已忽略，`curves/` 的 96 个整曲调教中间文件保留本机。随包模板 `vocaloid_bridge/templates/ai-starter.vpr` 是项目自有的起始工程。

推送提交 `165a478df47e78b4ef4f60a52963fca93952b09d` 成功，GitHub 回读为 PUBLIC、默认分支 `master`、`LICENSE` 识别为 MIT；远端文件树 315 个文件，`curves/` 为 0。

## 样式与细项参数修复（会话 38）

`style_capture` 保存预设后会把名称及 ID 写回来源声部，随后保存 VPR 可保留关联。`performance.set` 修改 Robot、Breath、Take 或 VoiceColor 参数时默认解除对应旁路，显式 `bypass` 优先。样式应用的 MIDI、音频效果和身份变更现在是一次原生事务，支持一次撤销；受支持的扩展工程也使用原有身份、曲线和数组保护。

普通样式、四类参数、显式旁路、单步撤销及重开通过：`artifacts/feature-acceptance-311dce7269c6/remaining.private_styles.json`。该批次的扩展夹具重复添加模板已有 Gain，准备阶段失败；修正夹具后 `artifacts/feature-acceptance-946acadda473/summary.json` 的扩展样式及清理通过，验证 root/track/part/note/tempo 和 MIDI/音频效果未知字段保留、撤销/重做与原始文件不变。原始两项故障回执 `artifacts/feature-acceptance-1ee00aa27368/summary.json` 保留。

原生语义预检 32 文件 / 211 引用零错误，Release 构建通过。未重跑全量，未新增合成音频或主观听音验收。已运行的客户端需保存并关闭工程，再重启 MCP 或调用 `vocaloid_runtime restart` 加载新宿主；本会话没有直接暴露的 VOCALOID MCP 工具，未强制重启其他客户端。详见 [会话 38](docs/session-log/session-38.md)。

## 多片段混缩修复（会话 37）

修复目标片段完成后提前停止整个原生渲染队列的问题：现在必须同时满足目标波形有效和 `Sequence.IsFinishedRendering`，才停止队列、释放 Lua 控制器和发布 WAV。单段导出和混缩共用此路径，原有超时值保持不变。

实际 12 段工程原先单段成功、整体混缩在片段渲染阶段等满 120 秒，回执 `artifacts/feature-acceptance-1f0384208023/mixdown.project_fixture.json`。修复后单段 0.829 秒，随后整体混缩 0.203 秒，生成 65.142857 秒、2,872,800 帧、44100 Hz、24 位双声道 WAV，12 段均有非零样本；回执 `artifacts/feature-acceptance-e83d8be0e2a2/summary.json`。原生语义预检 32 文件 / 211 引用零错误，Release 构建通过，没有重跑全量套件。

原始工程未覆盖。活动宿主仍持有启动时的程序集副本；保存并关闭工程后重启 `vocaloid6-native`，或调用 `vocaloid_runtime restart`，才会载入修复。当前聊天未暴露 VOCALOID MCP 工具，以上为独立真实 stdio MCP 验收，未强制重启其他客户端。

## Agent 作曲流程（0.27.0）

起因是用户问功能矩阵的 P-13、L-08 是否影响做歌，并要求做歌需要的功能都能被 Agent 正常调用。

- **P-13 不影响做歌。** 它指工程的内部采样率能否设成 48000 或 96000 Hz 再合成人声。手册第 37 页写明 VOCALOID 的内部运行规格是 44.1 kHz，交付采样率在混缩时选择，44.1/48/96/192 kHz 均已验证。非 44100 工程的渲染和混缩明确报错，用 `sequence.update` 改回 44100 后渲染通过；该行改为 V。
- **L-08 不影响 AI 做歌。** 它指带 Attack/Release 的片段存入素材库再取回时是否完整。手册注明 Attack/Release 是标准 VOCALOID 声部的功能；实测在 AI 音符上设置后，渲染结果逐样本相同。素材往返可用，其余组合和实际演唱需要标准声库，该行保持 I。
- **审计。** `tools/check_ai_effect_audit_36.py` 用 asa 做了 88 项逐样本比较：34 项改变 AI 合成，53 项不改变，1 项被明确拒绝，与手册的 AI 参数表一致。没有逐个声库比较。

审计和 Haiku 子 agent 的试做暴露出会让 Agent 做错歌的问题，已修：

- **改词不改音。** AI 音符用 `note.update` 只改 `lyric` 时，文字变了，音素和唱出的声音不变。现在重新生成音素，渲染结果与 `lyrics_apply` 逐样本相同；受保护音符和显式音素保持不变，被拒绝的歌词不留下任何改动。
- **歌词写法无处可查。** 中文汉字和带声调数字的拼音会被原生转换器拒绝，原报错不说明原因。现在报错按语言给出写法，工具说明和流程写明一个音符一个音节：日语假名、英语单音节单词、中文不带声调的拼音。
- **新建声部没有默认音色。** 新声部的 Breath 等效果默认旁路，也没有音频效果；编辑器会套用声库的默认样式。流程把应用 `<声库名> Default` 样式列为固定步骤，21 个已安装 AI 声库都有这个样式。
- **调用成功但不发声。** `controller.types`、`dvqm_get` 标注适用声部，`vibrato.get` 返回类型名和取值范围，`voice.get/set` 附已安装声库的名称和语言。AI 颤音需要非 None 类型、时长和 depth 事件，且只演唱首个 depth 和 rate 值；VoiceColor 旁路时颜色值不生效。
- **流程入口。** 新增 `vocaloid_workflow`，原样返回 [作曲流程](docs/song-workflow.md)。`vocaloid_operations` 不带范围索取全部文档时报错，此前会超出客户端的结果上限。

| 范围 | 回执 | 结果 |
| --- | --- | --- |
| AI 表现控制逐样本审计 | `artifacts/feature-acceptance-ca89e374bac1/agent.ai_effect_audit_36.json` | 通过 |
| 指引、改词转换、适用性标注、完整做歌流程 | `artifacts/feature-acceptance-ee0bdfc0c02a/summary.json` | 4 项通过 |
| 受改动影响的既有用例重跑 | `artifacts/agent-song-36-evidence.json` | 19 项通过 |
| Haiku 子 agent 在 0.26.0 上试做 | `artifacts/agent-trial-haiku-36.json` | 42 次调用完成 |

本次共 21 批运行，3 批失败并保留回执：一次是审计的对照项用了当时不改音的改词操作，一次是用例对日语多音节歌词的预期写错，一次是同一调用里解除保护并改词时原生音符拒绝写入音素，已改为先解除保护。原生语义预检 32 文件 / 211 引用零错误，Release 构建零警告零错误，操作目录检查通过。没有运行全量套件。

Haiku 做出的 8 个音保留在 `output/haiku36-moon-rise.vpr`、`output/haiku36-vocal-part.wav` 和 `output/haiku36-mixdown-48k24.wav`。它们由 0.26.0 生成，没有人听过。

## MCP 托管启动

创建/打开工程按需启动 VOCALOID 私有实例；新增 `vocaloid_runtime` 管理 status/start/stop/restart。默认保护活动工程，确认进程退出后允许新建/重开；已派发请求的失联不自动重放。启动握手绑定缓存归属，退出后清理自有目录；MCP Python TEMP/TMP 也落在 E 盘。

定向证据：`artifacts/feature-acceptance-0dc851857340/runtime.lifecycle_35.json` 与 `artifacts/feature-acceptance-dba96773341c/runtime.no_replay_35.json` 分别通过；后者同批生命周期夹具缺声库初始化的失败保留，修正夹具后单独通过。两项在 0.27.0 重跑通过。

## 已完成的剩余实现

- **复杂时间编辑**：MIDI/AI 与音频片段内部边界自动拆分；插入/删除同属一次原生事务，保留受支持的音符、音高、控制器、音量、声像和片段元数据；起始 tempo 删除与拍号边界纳入原生时间操作。
- **素材元数据 v2**：MIDI 素材携带控制器、直接音高与其他数组字段；音频素材携带片段、region、效果元数据，使用波形摘要绑定。导入、效果及元数据一次提交，源 WAV 在操作期间只读锁定。v1 元数据继续可读。
- **其他数组**：voices、语言列表、效果/参数、颤音、音素位置等对象数组按所属实体、自然键和已知字段投影映射；无法区分的冲突在提交前报错，不按数组下标猜测来源。非选中字段丢失时回滚，显式替换或删除按操作语义更新元数据。
- **事务边界**：读回在提交前完成，读回异常仍可原生回滚；元数据变动但原生地图相同的 tempo/拍号合并建立原生历史，相同地图及元数据为 no-op。

此前 0.24.0 的冲突决策、21 AI 声库首音符、完整歌词、扩展拆合/复制/迁移、归档素材属性保持继续保留；创建、打开、编辑、保存入口保持。

## 0.25.0 的必要验证

只执行对应改动的定向用例，没有全量重跑。

| 范围 | 回执 | 结果 |
| --- | --- | --- |
| 跨 MIDI/AI 和音频边界插入/删除、曲线迁移、起始 tempo、撤销/重开 | `artifacts/feature-acceptance-fadfaa5525c3/completion.timeline_34.json` | 通过 |
| 数组编辑、MIDI/音频元数据捕获导入、历史及重开 | `artifacts/feature-acceptance-f83d17ee2ba4/completion.media_arrays_34.json` | 通过 |
| 元数据地图合并/no-op、提交前读回故障回滚 | `artifacts/feature-acceptance-a8b0f5edcf1d/completion.transactions_34.json` | 通过 |
| 原生暂存快照 | `artifacts/session34-staged-save/result.json` | 写出暂存值后仍 staged，原生 rollback 恢复原值 |

最初两个用例因测试夹具未初始化颤音类型/时长失败；修正后时间删除暴露音频 region 未加入唯一键，补齐后通过。原失败回执保留，不将所有历史批次称为全绿。

## 连接与交付状态

会话 36 在新建的 Claude Code 聊天中确认了 0.26.0 的客户端绑定：该聊天自身的 MCP 连接列出 38 个工具，单次 `vocaloid_status` 返回 `mcp_version=0.26.0`、原生引擎 6.13.3.1、0 会话，实际 desktop 与预期私有 desktop 一致。回执：`artifacts/mcp-binding-confirmed-36.json`。原 Codex 聊天在全局重载后仍返回 `Transport closed` 的旧绑定没有再重试，阻塞记录 `artifacts/mcp-binding-blocked-36.json` 保留。

0.27.0 尚未经客户端绑定确认。服务进程只在启动时载入代码，这个聊天的连接在 0.27.0 完成后仍报告 0.26.0；独立 stdio 连接已确认 0.27.0 和 39 个工具。用户在客户端里重新连接 `vocaloid6-native` 或新开会话后，Agent 才能看到新的工具说明和 `vocaloid_workflow`，见 [TODO](TODO.md)。

受测结果不代表任意未来 schema、物理断电/损坏存储、硬件 MIDI、真实 DAW 或主观音质验收；这些不属于用户要求。

[功能矩阵](docs/feature-matrix.md) 还有 7 个 I 行。C-09、C-11、C-16、L-08 的未验部分需要经典 DSE 声库，U-02 需要物理 MIDI 设备，U-01 需要实际听音；这三类按固定约定不属于验收范围。M-08 余下的是不接管的用户编辑器全局播放开始模式。

## 清理

会话 34：删除 525 个自有临时文件，共 7,240,806 字节，包括已停止旧宿主的两个 C 盘独立缓存命名空间。

会话 36：这个聊天拉起的两代实例都已用 `vocaloid_runtime stop` 结束。删除 74 个自有文件，共 7,325,447 字节：测试生成的 VPR/WAV、空的 stderr 日志和构建临时文件，见 `artifacts/cleanup-36.json` 与 `artifacts/cleanup-36b.json`。私有进程临时目录和 MCP 临时目录为空。更早会话遗留在 `.runtime` 的 430 个 stderr 日志（18 个非空）和 8 个宿主运行副本目录没有确认归属，保持原样。实例正常停止后仍会留下一个空的 stderr 日志，代码没有改这一点。
