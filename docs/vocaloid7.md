# VOCALOID7 兼容说明

## 选择与构建

0.29.0 起支持本机 VOCALOID6 和 VOCALOID7，0.30.0 补齐 V7 参数检查与原生 AI 生成入口；构建统一使用 .NET 10 Windows Desktop。`tools/setup.ps1` 默认根据注册表、Program Files 目录及核心 DLL 的实际文件版本选择最新安装；运行时每个新宿主使用同一选择器。活动宿主固定产品、版本及路径，不在工程中途切换。

`VOCALOID_INSTALL` 或 `setup.ps1 -Install` 可明确覆盖目录。`-Product` 用于校验选择结果，不会忽略已发现的目录另找同名安装。发现不支持的更新产品会报错，不能据此承诺未来 VOCALOID8 自动兼容。

```powershell
pwsh -NoProfile -File tools/setup.ps1
pwsh -NoProfile -File tools/setup.ps1 -Install 'C:\Program Files\VOCALOID6\Editor' -Product VOCALOID6
```

产品输出是 `native/bin/Release/<product>/net10.0-windows`，中间文件也按产品分开。标记绑定产品、核心程序集、安装目录、版本、框架和宿主摘要。缺失、过期或错误产物会提示 setup，不启动旧 DLL。安装更新后重新构建，再保存关闭活动工程、重连 MCP。注册名 `vocaloid6-native` 和既有任务标签保持兼容。

## 行为差异

| 范围 | VOCALOID6 | VOCALOID7 |
| --- | --- | --- |
| 声库、样式、表现、Singing Skill | 片段级 | 显式 `scope="track"`，影响整轨 |
| 声库身份 | 片段 `aiVoice`/`voice` | 轨道 `voice` 与 `voiceTypeID` |
| AI 类型初始化 | 原有行为 | 打开/克隆/导入时，只为空类型补同声库原厂默认值，返回 `initialized_voice_types` |
| 颤音 | `ai_enabled` | `curve_model`，支持值由 `vibrato.get` 返回 |
| Take | `take_lane` | `take_number`，使用原生范围 |
| VMM 素材库 | 保留 | `media_*` 明确不支持 |
| 音频效果 | 主、轨道、片段 | 主、轨道；片段级明确不支持 |
| WOR 反转/变声 | 保留 | `reverse`/`voice_change` 明确不支持 |

文件级编曲优先使用 V7 轨道 `voice`，兼容旧片段 `aiVoice`；新 V7 音符使用 `vibrato.aiCurveModel`，显式源音符保留原有字段。原生加载及保存仍核对轨道数量、类型和声库 ID，未知字段与资源继续由原有归档保护管理。旧 V6 工程在同轨使用不同片段声库时，无法无损映射为一个 V7 轨道声库，身份不一致会被拒绝。

原生 `MidiAi`、声库 `IsAi` 和编辑器面向用户的轨道名称不作未经验证的等同。实测 V7 引擎能用已安装 V6 asa 完成当前模板的合成；这不是全部旧声库或轨道组合均已验收的保证。

## 截图功能到 MCP

先用 `vocaloid_features` 查功能及操作映射，再用 `project_inspect` 读取目标的实际范围、枚举与调用参数。V6 历史功能矩阵单独保留，不代表 V7 验收。

| 截图控件或编辑目标 | 可调用入口 | 范围或说明 |
| --- | --- | --- |
| VOICE 声库 | `voicebanks`、`voice.get/set` | V7 显式 `scope="track"` |
| TYPE（Normal / Power 等） | `voice.get` 的 `voice_types`、`voice.set` 的 `voice_type_id` | 使用所选 V7 AI 声库真实 ID，不按名称猜测 |
| STYLE | `style_list/get/apply/capture/update/delete` | 轨道样式，系统预设只读，自建预设独立保存 |
| ROBOT VOICE | `performance.get/set` 的 `robot_mode`、`bypass.RobotVoice` | 真实枚举及开关 |
| BREATH、EXHALATION | `breath_mode`、`breath_type`、`breath_exhalation`、`bypass.Breath` | 范围以读回为准 |
| VOICE COLOR 开关 | `bypass.VoiceColor` | `false` 启用，`true` 旁路 |
| EXPRESSION / AIR / CHARACTER / ATTACK | `voice_colors.S5Expression/S5Air/S5Character/S5Attack` | ATTACK 要求 V7 AI 声库，不是旧版 `dvqm` Attack |
| TAKE | `performance.set` 的 `take_number` | 影响轨道全部片段，先读回最大值 |
| 轨道静音、独奏、名称、录制使能 | `track.list/update` | 录制使能不等同开始录音 |
| 音量、声像 | `automation.list/set/remove` | `track_volume`、`track_pan`；主轨为 `master_volume` |
| TEMPO、TIMESIG | `tempo.list/set/remove`、`time_signature.list/set/remove` | 原生 tick 和小节索引 |
| 音符、歌词、音素 | `note.*`、`lyrics_apply`、`phonemes_apply` | 逐音与批量入口；文字修改和音素转换需区分 |
| 音高、颤音、表现、发音时值 | `pitch.*`、`vibrato.*`、`note.update.ai_expression`、`phoneme_timing.*` | 原生曲线与范围读回 |
| 伴奏、播放、停止、定位、混缩 | `project_audio` 对应导入、transport、mixdown 操作 | 私有宿主，不操纵用户编辑器 |
| 撤销、重做、批量操作 | `undo`、`redo`、`batch.run` | batch 首次失败停止，之前完成的操作保留 |
| 网格、缩放、面板、角色插图 | 界面专属，未提供前台控制 | AI 使用显式索引、tick 与曲线坐标编辑工程 |

V7 合成音高可通过 `pitch.set` 的 `from_rendered=true` 转成可编辑直接音高。默认拒绝覆盖已有曲线；只有显式 `overwrite_existing=true` 才替换。`vibrato.set` 的 `reset_ai_defaults=true` 调用原生 AI 默认颤音恢复，不是本地随机调参。

## 原生 AI 自动生成

`project_ai_adjust(session_id, track_index, part_index)` 调用真实 `ai.generate`，生成选中 AI 片段的演唱缓存。默认不改手绘曲线；`preserve_pitch=true` 将生成音高保留为可编辑曲线，`note_indices` 可选定音符，已有曲线必须显式 `overwrite_existing=true` 才替换。多个音符在一次原生事务中固化，可一次撤销。

`take_number` 是可选整轨修改，后续生成失败不会自动撤销 Take，回执会明确说明。`ai.status` 和 `project_inspect(feature="ai_adjust")` 读回缓存有效性、渲染是否结束及各音符已有点数。曲线固化后缓存可以重新变为待生成，应区分完成观察与当前有效性。

该入口是 VOCALOID:AI 根据音符、歌词及参数进行的原生生成，不宣称存在独立“一键评选最佳唱法”的接口。它不保存 VPR，也不导出交付 WAV；调用后分别用 `project_save`、`project_render_part` 或混缩导出。

## 本轮独立验收

会话 46：41 工具、130 操作，V7 功能导航 39 项（包含明确不支持项）。V6/V7 语义预检均为 35 文件/218 引用/零错误，V7 构建通过；本轮未构建或动态复验 V6。

- V7 归档身份正负例 7 项通过。不同主/副声库的同形轨道可区分；同身份的未知字段冲突、声库丢失继续拒绝。
- GekiyakuV Normal/Power 切换、默认 Style、四类 Voice Color、Robot/Breath/Exhalation、batch 编辑与参数历史通过。修复 Robot 轨道便利方法依赖编辑器 App 的问题。
- AI 生成、默认颤音恢复、两个音符 129/190 个点的保留、单步撤销/重做、防覆盖、保存重开通过；root/track/part/note/voice/effect/参数未知字段与额外 ZIP 资源保持，源文件不变。
- 重开后非静音 WAV 为 342877 帧，44100 Hz mono PCM16，peak 0.1215209961，RMS 0.0152129538。结束时零会话，无自有进程抢占前台。

实际 stdio 回执为 `artifacts/feature-acceptance-78bc268d0a70/summary.json`，早期失败与修复记录见 [会话 46](session-log/session-46.md)。未逐项比较所有参数音色变化、未验任意扩展组合、未做人耳试听。当前聊天没有暴露 VOCALOID 工具，客户端需保存关闭工程后重连，检查 41 工具及 `project_ai_adjust`。

## 0.29.0 初始证据

- V6 6.13.3.1、V7 7.0.0.1：语义预检和分开构建通过。
- V7 默认选择：真实 stdio 编曲、自动音素、保存重开、374850 帧非静音 WAV，通过；`artifacts/background-demo-b575e1fb9f.json`。
- V6 显式覆盖：同流程 374849 帧非静音 WAV，通过；`artifacts/background-demo-603fccdd6a.json`。
- 新 V7 asa `BXHPECHANDRW3XEL`：新建、自动音素、纯 V7 文件替换及重开保持 ID 和默认类型，通过；`artifacts/v7-native-roundtrip-05554c8b.json`。该项没有渲染。
- 两次 stdio 合成结束后零会话，前台窗口不变。当前聊天未直接连接 VOCALOID MCP；客户端重连待用户执行。

V7 混缩、全部样式/表现参数的声音效果、复杂扩展迁移、设备与 DAW 尚未逐项运行验证。V6 [功能矩阵](feature-matrix.md) 不自动继承为 V7 证据；本次没有重跑全量套件。