# VOCALOID6 功能覆盖矩阵

目标：本机 Editor 6.13.3 / 原生程序集 6.13.3.1。基线：官方《VOCALOID6 Reference Manual V6.13.0》99 页，目录页 2-10；本机已安装的原生接口目录。

本清单覆盖功能语义，不将同一功能的菜单、按钮、快捷键重复计数。`native_api_catalog` 另外列出实际程序集类型、方法签名和不可调用原因。

## 状态规则

- **V**：有实际文件、音频或原生返回值的验收证据。
- **I**：已有受控入口或原生公开接口，尚未完成本轮逐项验收。
- **M**：尚未实现完整入口。
- **X**：会操作用户前台、全局设置或授权，不符合当前约束。
- **E**：需要外部设备、DAW 或其他未提供的环境；不是已验证功能。

V 不由工具数量或能够枚举签名推导。当前为 36 个工具、119 个结构化操作；[历史完整回执](../artifacts/feature-acceptance-012574702338/summary.json) 的 76 通过、5 失败、2 个缺样本项保留。会话 08 新增静音设备传输、会话冻结、未知数据保留与相应定向证据；经典声库、复杂扩展格式及外部环境仍有缺口。当前证据汇总见 [STATUS](../STATUS.md)，不宣称本轮重跑了完整套件。

## 工程与文件

| ID | 功能 | MCP / 原生入口 | 状态 | 手册页 |
| --- | --- | --- | --- | --- |
| P-01 | 新建独立工程 | project_create | V | 13-14 |
| P-02 | 打开 VPR | project_open | V | 14 |
| P-03 | 保存、另存为 VPR | project_save | V | 14 |
| P-04 | 关闭及显式丢弃修改 | project_close | V | 14 |
| P-05 | 工程名称、轨道数、脏状态 | project_status / project_edit sequence.get | V | 16 |
| P-06 | 工程调音设置 | tuning.get/set；手册项目设置的单位为 Hz，原生值直接传递 | V | 16 |
| P-07 | 撤销、重做及历史 | project_edit history.status / undo / redo | V | 17 |
| P-08 | 丢弃未提交的原生编辑 | project_edit history.rollback；真实 staged tempo 回滚 | V | 17 |
| P-09 | 恢复到上次保存状态 | project_revert | V | 14 |
| P-10 | 原生工程副本 | project_clone；音频源关闭后独立导出已验，非所有素材组合保证 | V | 17 |
| P-11 | 用户编辑器最近文件列表 | 不改用户全局偏好 | X | 14 |
| P-12 | 用户编辑器自动保存设置 | 不改用户全局偏好 | X | 24 |
| P-13 | 原生内部采样率与预送信息 | sequence.update 的采样率读写已验；presend_time_sec 原生只读；声乐合成限定 44100，输出率另见 X-03 | I | 原生 API |
| P-14 | 自定义字段与额外工程资源保留 | root/master/track/part/note 与固定嵌套对象、资源、重排及历史通过；复杂数组/复制语义仍受限 | I | 格式扩展 |
| F-01 | VPR 导入 | project_import；修改、保存、重开和源文件保护已验 | V | 15 |
| F-02 | VOCALOID3/4 VSQX 导入 | project_import；两份样本音符数据已验，经典身份往返需 DSE 声库；丢失身份时保存前报错 | E | 14-15 |
| F-03 | PPSF V2 导入 | project_import；497 个音符保留，经典完整往返需 DSE 声库；类型转换与身份丢失已有显式保护 | E | 14-15 |
| F-04 | MIDI/SMF 原生导入及编码选择 | project_import；UTF-8 样本往返 | V | 15 |
| F-05 | 原生 SMF 导出及歌词编码 | project_export_midi；UTF-8 歌词与时序往返 | V | 15 |
| F-06 | 文件级 MIDI 读写 | midi_read / midi_write | V | 15 |
| F-07 | 导入到已有工程而非新会话 | project_merge；MIDI 片段样本 | V | 15 |
| F-08 | 仅导入速度与拍号 | project_merge include_tracks=false / replace_tempo=true | V | 15 |
| F-09 | 独立输出、默认不覆盖、原件保护 | 原生路径与文件保护 | V | 14-15 |
| F-10 | PPSF V3 导入 | 作者公开 Monologue.ppsf，PPSF3.2、1 条 NT 轨和 190 音符的原生导入、VPR 保存重开已验；不等于 NT 声库可用于 VOCALOID 合成 | V | 14-15 |

## 轨道、片段与事件编辑

| ID | 功能 | MCP / 原生入口 | 状态 | 手册页 |
| --- | --- | --- | --- | --- |
| T-01 | 轨道枚举及属性 | project_edit track.list | V | 28-32 |
| T-02 | 新建 AI、传统人声、音频轨 | project_edit track.create / project_audio import_audio | V | 18 |
| T-03 | 轨道命名与颜色 | project_edit track.update；颜色为 0..15 调色板索引 | V | 31 |
| T-04 | 轨道删除、重排、复制 | project_edit track.remove / reorder / duplicate | V | 17-18,33 |
| T-05 | 轨道静音、独奏 | project_edit track.update | V | 30-31,73 |
| T-06 | 轨道音量、声像与自动化 | project_edit automation.list / set / remove；真实混音与工程往返已验 | V | 32,37,72-73 |
| T-07 | 轨道输出总线路由 | bus_no 参数持久化、bus 0/1 离线混缩已验；实际外部总线路由需要 DAW | E | 72 |
| T-08 | 轨道 MIDI 录音开关 | track.update midi_recording；会话内有效，重开恢复关闭 | V | 32,73 |
| T-09 | 轨道冻结与解除冻结 | track.freeze/freeze_state/unfreeze；会话自有缓存，保存/克隆还原作者状态；受测多片段及自动化通过 | V | 原生 API |
| R-01 | MIDI 片段枚举、新建 | project_edit part.list / create | V | 32-37 |
| R-02 | MIDI 片段名称与位置 | project_edit part.update / move | V | 33-37 |
| R-03 | MIDI 片段长度与右边界 | project_edit part.resize；左右音频边界见 A-03 | V | 32-37,44 |
| R-04 | MIDI 片段删除、复制 | project_edit part.remove / duplicate | V | 17,33 |
| R-05 | MIDI 片段分割与连接 | project_edit part.split / part.join | V | 18,33 |
| R-06 | 时间范围插入空白、删除时间 | project_edit time.insert / time.delete；跨 MIDI 片段内部边界须先分割 | V | 18 |
| R-07 | 选区与多选状态 | project_edit selection.get / selection.set | V | 12,17 |
| R-08 | 事件剪切、复制和跨工程粘贴 | project_clipboard；MIDI 轨道和音符样本，源关闭后仍可粘贴 | V | 12,17 |
| N-01 | 音符枚举、增加、删除 | project_edit note.list / add / remove | V | 39,45-49 |
| N-02 | 音高、时值、力度、位置 | project_edit note.update | V | 45-49,59 |
| N-03 | 音符复制、分割、连接 | project_edit note.duplicate / note.split / note.join | V | 17-18,45 |
| N-04 | 多音符批量移调与编辑 | project_edit note.batch_update；歌词文字和移调，保存重开已验 | V | 49 |
| N-05 | 歌词、音素、语言与保护 | project_edit note.add / update | V | 48-49,57 |
| N-06 | 逐音节写入与延音连音 | project_library lyrics_apply 原生音节分配；歌词文字批量另见 note.batch_update | V | 19,48 |
| N-07 | 歌词转音素、候选音素 | project_library 原生 G2PA；日语可合法返回空候选 | V | 19,48,57 |
| N-08 | 元音、辅音时序编辑 | phoneme_timing.get/set/reset；原生渲染后生成位置，保存重开再渲染读回通过 | V | 40,59 |

## 节拍、音高与表现

| ID | 功能 | MCP / 原生入口 | 状态 | 手册页 |
| --- | --- | --- | --- | --- |
| M-01 | 速度事件读取、增加、修改、删除 | project_edit tempo.list / set / remove | V | 31 |
| M-02 | 拍号读取、增加、修改、删除 | project_edit time_signature.list / set / remove | V | 31 |
| M-03 | 全局速度开关与值 | project_edit sequence.update | V | 16,74 |
| M-04 | tick、小节、秒和采样换算 | project_edit time.convert；原生时间映射 | V | 29-31 |
| M-05 | 主调音 | project_edit tuning.get / set | V | 16 |
| M-06 | 循环区间与开关 | project_edit loop.get / set | V | 20,29-30 |
| M-07 | 循环区间起止标记 | project_edit loop.get / loop.set | V | 20,29-30 |
| M-08 | 播放头与播放开始模式 | transport 的开始/停止/异步定位已验；用户编辑器的全局开始模式设置不接管 | I | 20,29-30 |
| C-01 | 参数曲线读取与编辑 | project_edit controller.list / set / remove | V | 50-51 |
| C-02 | 原有 VPR 曲线的文件级替换 | score_curve | V | 50-51 |
| C-03 | 直接音高曲线写入、清除 | project_edit pitch.list / set / clear；保存重开后回读 | V | 39,45 |
| C-04 | 音高工具、铅笔与橡皮的语义 | pitch.set/clear 原生点写入与擦除；不是交互工具切换 | V | 39,45 |
| C-05 | 颤音深度、频率、起止与开关 | vibrato.get/set；非空 depth/rate 事件和保存重开通过 | V | 40,59 |
| C-06 | 常规人声与 AI 表现参数 | note.expression_bounds / note.add / update；7 个传统及 12 个 AI 字段读写、保存重开已验，不等于各字段声音效果 | V | 40-43,59 |
| C-07 | 经典 Emotion 表现 | note.update expression.Accent、velocity 和 vibrato；真实经典声音与往返需 DSE 声库 | E | 41-43 |
| C-08 | 声库列表与可用性 | voicebanks | V | 43,53 |
| C-09 | 主、副声库与 AI 声库选择 | voice.get/set；双 AI 声库素材往返已验，传统声库需对应 DSE 资源 | I | 43,53 |
| C-10 | 样式预设查询及应用 | project_library；含音频效果链的样式保存重开 | V | 43,54-55 |
| C-11 | Singing Skill、Attack、Release | singing_skill_catalog/get/set 与 note_skill_get/set/reset；目录及参数可调，经典声音和完整往返需 DSE 声库 | I | 55,58 |
| C-12 | Robot Voice | performance.get/set；禁用原生结果缓存后 Hard 声音差异、保存重开和混缩通过，同宿主另一会话音频保持 | V | 43 |
| C-13 | Breath 模式、类型与呼气量 | 参数保存重开通过；启用、频率和呼气量有 PCM 差异，受测 AI 中 Male/Female 声音相同，不声称类型听感差异 | V | 44 |
| C-14 | Take 车道选择 | performance.get/set；0 与 9 车道声音差异及保存重开通过 | V | 44 |
| C-15 | MIDI 效果旁路 | performance.get/set；Robot、Breath、Take 与 AI VoiceColor 旁路/状态已有定向证据；Exciter 归入经典 VoiceColor | V | 43-44,55 |
| C-16 | VoiceColor 参数与声音 | 全 9 参数持久化；AI 的 S5Expression/S5Air/S5Character 及旁路声音差异通过，另 6 个经典参数声音需 DSE 声库 | I | 43-44,55 |
| C-17 | Take 原生参数与旁路 | 包装接口专属值为 Lane，另有通用 bypass；现有 performance 入口已覆盖，没有已发现的其他专属参数 | V | 44 |
| C-18 | AI Timing 表现 | phoneme_timing.get/set/reset；改动、保存重开、再渲染读回及重置通过 | V | 40 |

## 音频、混音与效果

| ID | 功能 | MCP / 原生入口 | 状态 | 手册页 |
| --- | --- | --- | --- | --- |
| A-01 | 原生人声片段渲染 | project_render_part | V | 19 |
| A-02 | WAV 导入音频轨 | project_audio import_audio | V | 15,37 |
| A-03 | 音频片段位置、边界与名称 | project_audio edit_audio | V | 32,37 |
| A-04 | 音频片段原始与处理资源导出 | project_audio export_audio；整资源导出，不等于裁剪区域渲染 | V | 19 |
| A-05 | 规范化 | project_audio process_audio normalize | V | 19 |
| A-06 | 反转 | project_audio process_audio reverse | V | 67 |
| A-07 | 时间拉伸 | project_audio process_audio time_stretch | V | 32,67 |
| A-08 | 音高偏移 | project_audio process_audio pitch_shift | V | 67 |
| A-09 | VOCALO CHANGER | project_audio process_audio voice_change | V | 67 |
| A-10 | 音频格式、峰值、RMS 与时长检查 | audio_inspect / project_audio inspect_audio | V | 19 |
| X-01 | 全曲主混缩 | project_audio mixdown | V | 15-16 |
| X-02 | 选择轨道导出与分轨 | project_audio mixdown / mixdown_stems；分轨旁路主效果与主自动化 | V | 15-16 |
| X-03 | 采样率、位深、声道 | mixdown；44.1/48/96/192 kHz、16/24-bit、单/双声道受测组合已验 | V | 16 |
| X-04 | 主、轨道、片段效果链查询 | project_audio effects | V | 52,60 |
| X-05 | 效果增加、删除、顺序与旁路 | project_audio set_effect | V | 60 |
| X-06 | 效果参数和预设 | project_audio set_effect；受测内置效果的参数及预设 | V | 60 |
| X-07 | Gain、De-esser、Compressor、EQ | effects/set_effect；全部有效参数量化读回、重开、受测预设和实际混缩 | V | 61-62 |
| X-08 | Distortion、Chorus、Phaser、Tremolo | effects/set_effect；全部有效参数量化读回、重开、受测预设和实际混缩 | V | 63-64 |
| X-09 | Auto Pan、Delay、Reverb | effects/set_effect；全部有效参数量化读回、重开、受测预设和实际混缩 | V | 65-66 |
| X-10 | 主音量自动化 | project_edit automation.list / set / remove；主混音及分轨旁路已验 | V | 31,73 |

## 媒体、环境与界面

| ID | 功能 | MCP / 原生入口 | 状态 | 手册页 |
| --- | --- | --- | --- | --- |
| L-01 | 媒体库列表、分类及搜索 | project_library 媒体接口 | V | 68-69 |
| L-02 | 媒体关键词与标签 | project_library 媒体接口；独立 property.json 持久化 | V | 69 |
| L-03 | 将 MIDI 媒体粘贴到工程 | project_library media_import | V | 69 |
| L-04 | 保存 MIDI 片段为媒体、修改属性 | project_library media_capture / media_update；仅工作区自有媒体 | V | 19,71 |
| L-05 | 删除工作区自有媒体 | project_library media_delete；禁止删除用户原有素材 | V | 71 |
| L-06 | 预设目录及音素语言信息 | project_library 目录查询已有原生返回值；具体经典效果的声音边界另见 C-11 | V | 53-58,77-91 |
| L-07 | 五种语言静态音素符号表 | project_library phoneme_table；手册参考数据，非原生动态枚举 | V | 77-91 |
| L-08 | 特殊表现素材的无损捕获 | 已验传统与 AI Attack/Release、无效音素标志；部分字段使用桥接扩展，其他特殊素材及组合待验 | I | 19,71 |
| L-09 | 非零起点的音频裁剪素材捕获 | project_library media_capture / media_import；PCM16 单声道样本跨速度变化逐帧验证 | V | 19,71 |
| L-10 | AI 次声库素材捕获与恢复 | project_library media_capture / media_import；两套已安装 AI 声库实际往返 | V | 19,71 |
| L-11 | 私有样式捕获、覆盖、改名、标签与删除 | style_capture/update/delete；原生 VSStyle 文件及应用后重开已验，用户原样式只读 | V | 54-55 |
| U-01 | 直接播放、停止、听音确认 | 指定 DirectSound 设备的静音播放/停止/定位/释放通过；实际听音质量仍未确认 | I | 20,29,39,45 |
| U-02 | 实时 MIDI/音频录制 | 需要独立设备与输入源 | E | 20,32,73 |
| U-03 | DAW、VST/AU、ARA 宿主同步 | 需要用户提供 DAW 宿主 | E | 74-75 |
| U-04 | 改变用户音频设备或全局偏好 | 不影响用户编辑器及设备状态 | X | 24-25 |
| U-05 | 窗口、面板、全屏、缩放、滚动 | 不操控用户交互编辑器 | X | 20-23,28-30,39,45 |
| U-06 | 鼠标工具切换、快捷键绑定 | 以受控编辑语义替代；不注入按键 | X | 26,28,39,92-98 |
| U-07 | 打开新闻、教程、帮助网页 | 不启动用户前台页面 | X | 13,27 |
| U-08 | 更新、下载内容与授权 | 不修改安装、账号或授权状态 | X | 27,76 |
| U-09 | 本机版本与原生接口目录 | vocaloid_status / native_api_catalog | V | 27 |

## 完成条件

所有可在当前约束内独立完成的功能都必须有实际入口和验收证据；M/I 行不能算作 V。E/X 不是成功，也不是静默回退。完整覆盖率以本文件及实际程序集目录共同核对，不以新增工具数量判断。

仍待完成：对应 DSE 声库下的经典身份、Emotion、Singing Skill、六个经典 VoiceColor，以及复杂扩展数据、实时输入/录制和 DAW 环境。原生设备传输已作静音验收，会话冻结及受支持的未知字段保留已具备入口和证据。内部合成率与输出率、离线求和与外部路由继续区分；静态音素表不是具体声库能力枚举，任意秒区间和尾长也不是当前原生混缩入口。前台窗口从未加入调用面。

官方来源：`https://rsc-net.vocaloid.com/assets/pdf_files/bb/VOCALOID6_Reference_Manual_6130_ENG.pdf`。本机原文缓存和抽取文本只保存在被忽略的 `.runtime` 中。
