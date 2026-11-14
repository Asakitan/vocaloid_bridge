# 当前状态

日期：2026-11-14。版本：0.30.0（含未发布修复）。41 个工具、130 个结构化操作；功能导航 V6 39 项、V7 41 项（含明确不支持项），不等于全量验收。

## VPRX 工程（会话 51）

- 修复 V7 原生 `.vprx` 工程被旧 `.vpr` 后缀检查拒绝：支持打开、导入、保存、还原、文件补丁、编曲和音符替换，扩展字段、嵌入资源与原文件覆盖保护保持。后缀不触发内容迁移；现有 `.vpr` 默认不变，V6 原生入口明确拒绝 `.vprx`。
- 双产品语义预检与独立 Release 构建通过。本轮三个功能用例在 V7 分组通过：归档/守卫 `2c741f35eabf`，编曲修正测试漏传必填参数后 `7566f0ec8393`；V6 同组三项加清理全部通过 `36cc8e4f2085`。未重跑全套，不修改下方历史计数；详细证据见 [会话 51](docs/session-log/session-51.md)。

## 剩余修复（会话 50）

- V7 最终受维护全套：165 通过、0 失败、13 原生不支持、8 阻塞、2 跳过，含清理；无传输错误、无遗留会话。回执 `artifacts/feature-acceptance-4edcb24890f5/summary.json`。全部 41 工具有通过用例中的正向调用，8 个媒体操作和 3 个经典 Singing Skill 操作仍无正向覆盖；不是 130 操作全功能完成。
- 修复合法音量/声像差异造成的同形轨道保存误拒绝；签名只取经过原生核对的已知曲线值，扩展多轨自动化变更先在原生克隆预检，真实身份碰撞在源会话修改前拒绝。修前新反例 `c92b18201037` 确认两类碰撞被误接受；修后 V7 全套和 V6 定向均通过。
- V7 媒体能力检查提前，不再误报归档事务问题；VSQX 缺经典声库时导入前拒绝原生隐式 AI 转换。修正版本作用域、旧拒绝预期和语言运行期缓存的验收；序列化语言、声库 ID、资源和历史继续严格核对。
- V7 Breath 已通过：多间隔试句测得 Often/Rarely PCM 差值 RMS 0.0015737608，保存重开保持，原阈值未改；旧试句不具区分力，并非已证实的引擎故障。
- V6/V7 语义预检各 35 文件/218 引用/零错误，专属 Release 构建成功；V6 共享变更定向为 7 功能用例加清理全部通过，回执 `artifacts/feature-acceptance-c12fa57e23c3/summary.json`，未跑 V6 全套。完整修改、阻塞及原生导出调查见 [会话 50](docs/session-log/session-50.md)。

## 全套验收与录音（会话 49）

以下为会话 49 历史结果；其失败处理和 Breath 结论以会话 50 为准。

- 修复后以同一 VSQX3/4、PPSF2/3 与手册夹具重跑 V7 受维护全套：143 通过、42 失败、1 阻塞、2 跳过，含清理；无传输错误。41 个工具在通过的用例中均被正向调用，但 8 个媒体操作和 3 个标准轨 Singing Skill 操作没有正向通过，不能称为 130 操作全部验收。回执 `artifacts/feature-acceptance-de3baf6e9e5d/summary.json`；该运行时临时关闭自动文件清理，缺少外部多片段 VPR。此后 Breath 和 VoiceColor 用例改用纯 V7 工程，尚未再重跑全套。
- VoiceColor 验收按产品分别使用 V7 轨道及 V6 片段作用域。V7 GekiyakuV 7.0.0 的 `S5Expression`、`S5Air`、`S5Character`、`S5Attack` 及旁路在受测短句均产生可测 PCM 差异，不适用 AI 轨的标准参数未写入；V7 定向 `artifacts/feature-acceptance-69705fa877b9/summary.json`、V6 `artifacts/feature-acceptance-8aefac3f9629/summary.json` 通过。未逐一验证其他声库或主观听感。
- 新的同代 V7 GekiyakuV Breath 定向用例读写轨道参数：启用与气息量分别产生 PCM 差异，但 `Often` 与 `Rarely` 在该句中逐样本相同；`Rarely` 的原生读回、保存重开及重新渲染仍一致，频率差异断言保留失败。回执 `artifacts/feature-acceptance-14556982650d/summary.json`；V6 原有用例通过 `artifacts/feature-acceptance-366540d779ee/summary.json`。这是单个声库与乐句的观察，原因未定位，不推断所有 V7 声库均如此。
- V7 7.0.0.1 + GekiyakuV 7.0.0：真实原生 `S5Attack` 从 0 调到 100，198450 帧 WAV 差值 RMS 0.01125779；音符 HMM 保持、撤销/重做及保存重开通过。V7 同代声库的旧 DVQM/HMM 冲突与 setter 顺序独立验证通过，回执 `artifacts/feature-acceptance-605da3f66ac3/summary.json`；V6 6.13.3.1 + asa 6.3.0 分开验证，回执 `artifacts/feature-acceptance-c0cbacbfa685/summary.json`。普通音符权重 `37/91` 保存正常，人工混入旧 Attack 后原生加载读为 `0/0`；该冲突不是 V7 的 `S5Attack`，也不是轨道 Singing Skill 效果。先 DVQM 后恢复 HMM 的受测撤销和两种顺序保存重开均未无损，保护保持；未试听、未验证所有声库。
- V7 安装版 `WAudioEffectManager` 只暴露 Master、Track、Converter 效果块及对应托管入口，效果窗口选择器只接受轨道或主轨；英文手册提及片段选择与安装版接口存在差异，未发现可用的独立原生片段效果路径，不排除另行实现桥接方案。
- 使用本地真实 VSQX3/4、PPSF2/3 与手册文本运行 V7 受维护全套基线：133 通过、48 失败、1 阻塞、2 跳过，含清理；回执 `artifacts/feature-acceptance-5c183883d42f/summary.json`。失败包含旧 V6 作用域、旧守卫预期、V7 不支持项及实际数据/环境问题，尚未逐项修复；不能将目录 130 项等同全部操作通过。
- 修复扩展工程一律拒绝 MIDI 录音的问题，录入复用原生音符新增的归档事务及曲线保护，并在提交前拒绝同形音符身份冲突。双产品冲突回滚、合成事件流、扩展音符/音高/控制器/自动化、资源、保存重开和撤销重做通过：V7 `artifacts/feature-acceptance-2099b6561503/summary.json`，V6 `artifacts/feature-acceptance-6be3fa3178a3/summary.json`；物理 MIDI 未验。
- 生命周期用例支持非零宿主代次和 V7 轨道声库作用域，操作目录用例保留 130 项名称/契约对照并允许产品说明；V7 定向 `eb3e327e743b`、`0584d924f85d`，V6 定向 `4661a69734e4` 均通过。修复后的全套结果见上文。
- 全套入口补入作曲流程与 V7 AI 控制用例；直接 AI 状态/生成、AI 调整、batch 和流程通过 `artifacts/feature-acceptance-b7f9a143fc21/summary.json`。普通工程暂存及音素时值的 V7/V6 定向通过 `925c506eb798`、`ccaf2d9aae12`；扩展工程反转后端及源数据保护通过 `b54a63201afe`、`24e361fb26fb`。
- 私有样式的捕获、修改、应用、效果、历史和保存重开按产品作用域分别通过：V7 `artifacts/feature-acceptance-b703e55eb213/summary.json`，V6 `artifacts/feature-acceptance-8dd41f7beddc/summary.json`。

## V7 音频反转（会话 48）

V7 安装版不再导出 WOR 反转渲染器；桥接对 PCM/IEEE 浮点 RIFF WAV 使用有界缓冲区逐帧倒序，返回 `native=false`、`backend=bridge.pcm_frame_reverse` 和时间元数据提示。多数据块合并为单块；有效的标准整数 `smpl` 循环端点和符合条件的 cue 点（含标签及区域）会重映射，播放列表关联或歧义 cue、分数循环、厂商扩展和其他时标保持原样并提示；压缩、未知扩展编码或不完整数据帧拒绝，源文件不改。V7 人声、多格式、多数据块独立解码、循环及区域 cue 正负例通过；普通、标签和跨块重复 cue ID 及 65536 项扫描上限的保护通过，回执 `artifacts/feature-acceptance-0cb552311264/summary.json`；V6 原生 WOR 反转与归一化回归通过，回执 `artifacts/feature-acceptance-d321081a9acd/summary.json`。详细边界见 [会话 48](docs/session-log/session-48.md)。

## 音符、样式与原生保护（会话 47）

- 会话 48 修复 V7 把有效通道静音误当成持久化静音标记：现从原生独立导出读取 `mute`，以 `channel_mute` 单独报告独奏影响后的有效状态；支持静音与独奏同时保存，并在其他轨道独奏时正确设置静音和恢复独奏。新增 V7 原生 `solo_state` 的 Off/On/Defeat 读写及发现，切换保留静音。AI/音频轨、多独奏轨、保存重开、三态切换和原生混缩对照通过；独立静音/独奏在受测工程不产生原生撤销项。V7 回执 `artifacts/feature-acceptance-1fb9dfec16f3/summary.json`，V6 对三态参数明确拒绝及兼容回执 `artifacts/feature-acceptance-f947acdb74c1/summary.json`。旧首音符测试已适配 V7 轨道声库作用域，回执 `artifacts/feature-acceptance-f5c1f1d24b4d/summary.json`。
- V7 乐谱分类在枚举名称收紧前的最终轨道状态改动后，17 项及清理全部通过：`artifacts/feature-acceptance-af3cbb665192/summary.json`；扩展工程身份、未知字段及清理通过：`artifacts/feature-acceptance-5bebf6ac713e/summary.json`。这些是分类和定向验收，不是全部功能验收。
- V7 归档轨道身份包含 `soloState`；独奏状态不同的同形扩展轨道可重排与重开。V6/V7 对扩展工程的轨道身份修改先在隔离副本预检，产生真实碰撞时原会话不变；V7 回执 `artifacts/feature-acceptance-ae04d8be8cbc/summary.json`，V6 回执 `artifacts/feature-acceptance-9922cd58c241/summary.json`，合法扩展编辑回执分别为 `44a6952d9af5`、`ec79f1de0dc3`。
- 修复轨道复合更新中原生拒绝名称后仍留下静音/独奏变更的问题；失败时恢复不进入原生历史的状态，恢复失败则标脏并报告。受测超长名称与录制开关组合在 V7 `artifacts/feature-acceptance-c47a027d0f83/summary.json`、V6 `artifacts/feature-acceptance-69e7bdec4560/summary.json` 均未留下状态或历史变化。
- 产品专属私有宿主故障注入先确认静音、独奏和录制均关闭，再改变三项并触发提交前失败；双产品均恢复轨道、音符、脏状态与历史：V7 `artifacts/feature-acceptance-97caf450ad44/summary.json`，V6 `artifacts/feature-acceptance-3b3f08ae53a3/summary.json`。歌词回滚探针不再误用旧版 V6 宿主。
- 修复乐谱名称枚举误接受数字字符串：轨道类型、V7 独奏状态、表现模式、音色和旁路键、控制器类型按名称校验，原有大小写规则保留。V7 `artifacts/feature-acceptance-b229734e56f5/summary.json`、V6 `artifacts/feature-acceptance-c67b15fd5ad1/summary.json` 的正负例及清理通过；修前真实误接受回执为 `artifacts/feature-acceptance-8b6d72a35eb3/summary.json`、`artifacts/feature-acceptance-68b1d3c0bc40/summary.json`。
- V7 工程生命周期、原生合成共 7 项及清理通过：`artifacts/feature-acceptance-8344e012cb7b/summary.json`。
- 会话 48 修复空 `dvqm_clear` 把工程标脏、使引用失效及被扩展/冻结保护误拒绝：仅原生选择已空时作为只读空操作，非空写入保护不变。扩展工程回执 V7 `artifacts/feature-acceptance-ce0ac0631c41/summary.json`、V6 `artifacts/feature-acceptance-a0cc24253bbe/summary.json`；冻结轨道回执 V7 `artifacts/feature-acceptance-7c13162b245b/summary.json`、V6 `artifacts/feature-acceptance-6570641b3c18/summary.json`。
- AI 音符可显式使用 `storage="bridge_metadata"` 读写独立 Attack/Release 注记，回执 `native=false` 且不影响 AI 合成；原生 DVQM 写入保护不变。功能发现、保存/重开、克隆、撤销/重做、音符删除/复制/拆合、权重编辑、冻结及未知字段保护通过；受测工程写入注记前后原生人声逐样本一致，V7 回执 `artifacts/feature-acceptance-edbda98e1c1e/summary.json`、V6 `artifacts/feature-acceptance-fbcfee057c8b/summary.json`。
- V6/V7 隔离实验确认 AI 音符同时包含非空 Attack/Release 和 Singing Skill 时原生重开会丢失后者。现在原生打开与文件输出均拒绝该冲突；调用方可检查后显式删除任一整棵子树并另存，受测剩余数据、资源及原文件不变。Attack/Release 两种冲突和两种修复选择在 V7 `artifacts/feature-acceptance-b48c40ba8f6a/summary.json`、V6 `artifacts/feature-acceptance-8936678672bb/summary.json` 通过；这不是双表示无损共存。
- 会话 48 解除扩展工程冻结的误拦截并补齐冻结发现模板：V6/V7 受测未知字段、音高、控制器、自动化、效果及资源在冻结、保存、克隆、重开和解除后的撤销/重做中保留；冻结缓存预送补偿后的 PCM 与冻结前混音按 2/32768 容差对照通过，已有 Attack 的清除仍被拒绝。V7 回执 `artifacts/feature-acceptance-382ecd42cead/summary.json`，V6 回执 `artifacts/feature-acceptance-bc5654ce2c9d/summary.json`；不声称所有扩展组合或实时播放路径均已验证。
- 音符删除底层可用；功能导航现提供绑定的 `note.remove`、`note.clear` 等模板，并提示结构变更后刷新索引。V6/V7 实际调用及保存有定向证据，V7 扩展工程另验证撤销和保存重开。
- 样式音频效果先准备原生控制器并应用模式，再转换其他参数，修复 Chorus 模式下的合法参数被拒绝；V6 片段效果从实际参数表读值及模式相关范围。V7 Chorus、Phaser、Reverb 具体预设均经过保存重开和撤销验证。
- V6/V7 AI 音符的原生 DVQM 写入及非空清除无法可靠保留 Singing Skill 和撤销历史，结构化和反射入口均明确拒绝；已有选择仍可读取，V7 `S5Attack` 是独立参数。已有 Attack/Release 的 AI 音符拒绝 note skill 写入；安全的普通及受支持扩展工程可编辑 note skill，目标未知子树仍拒绝。
- V6/V7 语义预检各 35 文件、218 引用、零错误，两个 Release 宿主构建通过。V7 关键用例与清理 6 项通过：`artifacts/feature-acceptance-0e95b9aeeed5/summary.json`；V6 三项及清理通过：`artifacts/feature-acceptance-dbcc3e8024fd/summary.json`。扩展工程与反射冲突保护分别见 V7 `artifacts/feature-acceptance-45e983f01064/summary.json` 和 V6 `artifacts/feature-acceptance-e449e555e781/summary.json`。
- 效果查询前后的序列化工程、脏状态和原生撤销历史一致：V6 `artifacts/feature-acceptance-9e59fd35aaf4/summary.json`，V7 `artifacts/feature-acceptance-e725bd16f983/summary.json`；未以此宣称音频逐样本无变化。
- V7 原生人声作为音频输入，双轨 44.1 kHz 立体声主混缩与分轨相加对比、主效果作用及 192 kHz 单声道导出通过，回执 `artifacts/feature-acceptance-4c197f2d178a/summary.json`；未据此推断所有工程或设备组合。
- 独立 stdio 证据不等于当前聊天已连接新宿主；未重跑全量 130 操作，未验证所有扩展组合或主观听音。此前逐样本证据与新保护范围的关系见 [会话 47](docs/session-log/session-47.md)。

## 0.30.0：V7 工程保护与 AI 调整

- 修复 V7 轨道主/副声库未纳入归档指纹造成的同形轨道误拒绝；真实身份冲突及声库表缺失仍拒绝，未知字段不清空。
- 新增 `project_inspect`，按截图功能读取实际参数、枚举与范围；`vocaloid_features` 区分 V6 历史证据和 V7 调用契约。Voice Type 可选择，Attack 按声库代际校验，Robot 模式修改不再调用交互编辑器的 `App.SequenceManager`。
- 新增 `project_ai_adjust` 与 `ai.status/generate`：使用原生 VOCALOID:AI 生成演唱数据，可选择 Take 和将生成音高保留为可编辑曲线；默认不覆盖已有曲线。支持原生 AI 默认颤音恢复，多个音符保留为一次可撤销事务。生成不是独立审美优化，也不自动保存 VPR 或导出交付 WAV。
- 验证：V6/V7 语义预检各 35 文件、218 引用、零错误；V7 Release 构建通过。修后身份保护 7 项正负例通过；真实 stdio GekiyakuV 的 Style、Voice Type、参数、batch、AI 生成、双音符固化、撤销/重做、防覆盖、未知字段与资源保留、保存重开及非静音渲染通过。固化点数 129/190，WAV 342877 帧、peak 0.1215209961、RMS 0.0152129538。

证据：`artifacts/feature-acceptance-78bc268d0a70/summary.json`；该运行 2 项通过（功能用例及清理），结束后零会话、无自有进程抢占前台。早期夹具声库选择错误、Robot App 依赖和 Python 回执解析失败均已修复，原回执保留，见 [会话 46](docs/session-log/session-46.md)。会话 46 当时未重跑全量套件、V6 构建或主观听音；会话 47 的 V6 构建与定向证据见上文。

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

两次 stdio 合成结束后会话数均为 0，前台窗口保持不变。安装选择器的 6 项定向检查、取消连接失效检查和 V6/V7 文件音符身份检查通过。没有重跑全量功能套件。会话 44 当时的 V7 VMM、片段效果、WOR 反转和变声均明确拒绝；会话 48 增加了受限格式的桥接反转路径。复杂扩展迁移及全部参数声音差异未逐项验收。当前聊天未暴露 VOCALOID MCP 工具，以上是独立真实 stdio 与原生客户端证据，不是当前聊天已重连的证明。

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
- **L-08 的历史证据。** 早期 asa 对照中 AI 音符上的 Attack/Release 未改变逐样本渲染，V6 既有选择可随受测素材往返。会话 47 发现原生编辑会损伤 Singing Skill 或撤销，AI DVQM 写入现已拒绝；其余组合和标准声部实际演唱仍待验证，该行保持 I。
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
