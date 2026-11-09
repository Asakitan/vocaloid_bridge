# 当前状态

日期：2026-11-10。版本：0.13.0。完整目标继续进行，不把受测范围扩大为所有输入与环境组合。

会话 09：用户明确选择仅使用 VOCALOID:AI 声库；不安装经典声库试用，继续扩展 AI 工程编辑及后台设备能力。
未指定类型的 `track.create` 默认改为 `MidiAi`；空工程到显式选声、编辑、保存重开和合成的定向验证见 `artifacts/feature-acceptance-32f1c9da5151/summary.json`。显式 `Midi` 类型及旧工程保护保留。

会话 10：带未知实体字段的音符及片段拆合、冲突回滚和历史有定向 MCP 验证；AI 剪贴板剪切/迁移、工程合并及旧历史、MIDI 错误回调的定向检查通过。DAW 固定命名管道隔离和真实 MIDI 硬件仍待验证。

会话 11：源 root/master 的直接与受测嵌套未知字段可在受控合并中保留，支持冲突预检及合并历史；独立虚拟 MIDI 输入的实际 WinMM 回调和清理通过。随机合成管道的同 profile 双向通信已观察，实际插件隔离仍待验证。

会话 12：受测速度事件未知字段支持编辑、历史和重开；剪贴板粘贴先验证独立候选；轨道合并支持受测不透明资源的冲突保护和历史。自有合成 DLL 的静态导入映射实验通过，实际插件隔离仍待验证。

会话 13：AI 剪贴板选择迁移工程级不透明资源；速度事件扩展按 tick 合并；拍号事件扩展支持编辑与历史。合成 ANSI 探针观察到动态解析、其他模块和初始化时序绕过静态 IAT 修改，实际插件隔离仍待验证。

会话 14：拍号扩展按原生逐事件时间换算合并；控制器事件扩展支持受测编辑与历史；音频轨及片段扩展迁移覆盖原始和处理后 WAV。带扩展工程的原生合成、MIDI 导出与离线混缩通过独立快照调用。

会话 15：控制器扩展支持受测轨道/片段复制、拆合及边界生成点，提交前校验保留的原生曲线；带扩展工程可执行独立 WAV 处理和受测私有素材操作。普通工程音频导入/编辑接入原生撤销历史。

会话 16：受测 AI 素材可携带片段和音符未知字段，并在候选快照预检后导入；扩展工程可通过独立快照进行静音原生传输；普通工程效果器直接编辑具有撤销重做。扩展时间编辑仍由原守卫保护。

会话 17：修正音高局部清除的半开区间与原生包含终点差异；纯元数据及资源合并可建立原生历史并撤销/重做。扩展时间及音符数组原生身份探针发现生成边界事件和 `ZeroPitch`，相关守卫保留。

会话 18：受测 MIDI/AI 实体未知字段支持受限时间插入/删除；受测 `directPitches` 项未知字段支持同音符编辑和原生历史。相同空工程合并保持目标脏状态与历史；音高写入增加提交前锚点校验。

## 当前入口与实测

- 37 个 MCP 工具，68 个乐谱、16 个音频、30 个素材、5 个剪贴板和 6 个 MIDI 录制操作，共 125 个。创建、打开、编辑、保存、关闭、克隆和恢复保留。
- `project_midi` 提供设备枚举、显式设备或事件流录制、状态、停止和取消；事件流的音符、速度映射、保存重开与静音 transport 同步已验。独立虚拟输入已触发实际 WinMM 回调；输入错误通知、回调故障和溢出的提交保护另有逻辑测试。
- 新增 `devices` 与 `transport_prepare/status/play/stop/seek/release`：明确选择设备，原生 VAE 独立播放；不改系统默认设备或用户编辑器。DirectSound 静音时钟、停止、异步定位、释放后保存、关闭自动释放通过。
- 新增 `track.freeze/freeze_state/unfreeze`：只持有会话自有缓存；修正预送时基、多片段范围和重复音量/声像处理。保存与克隆写出原始作者状态，冻结缓存不持久化。多片段、非零起点、Gain 和音量自动化的受测混音差异约 0.054%。
- 修复原生保存/克隆丢弃未知工程数据：保留 root/master/track/part/note 未知字段、固定嵌套对象字段，以及额外 ZIP 资源；仅覆盖未知键，不恢复旧的已知值。原生实体通知和真实历史边界防止删除重建时元数据错贴。
- 未知数据覆盖包括已验证的重排、更名、音符移动/修改、轨道/片段/音符复制、AI 和音频剪贴板剪切/跨工程粘贴、工程合并、音符及片段拆合、速度/拍号/控制器事件扩展、控制器扩展的工程内复制拆合、受测不透明资源及音频资源迁移、删除同值新建、撤销/重做、参数编辑、保存重开，以及源关闭后的克隆。控制器扩展跨工程迁移、其他数组和更广泛音频资源组合仍有明确限制。
- 0.2.1 的 Robot 零结果缓存修复、19 个音符表现字段、VoiceColor 适用性、Take/Breath/AI VoiceColor 声音证据和真实 PPSF3 样本继续保留。

## 本轮证据

构建：0 警告、0 错误。只运行改动相关检查，未重跑完整历史套件。

| 范围 | 回执 | 结果 |
| --- | --- | --- |
| 扩展时间、音高项、原有保护和工程历史 | `artifacts/feature-acceptance-1de6c1d0abc4/summary.json` | 10 个功能用例及清理共 11 通过，无自有前台切换或遗留会话 |
| 音高与控制器混合扩展 | `artifacts/feature-acceptance-97ee96429bd9/summary.json` | 定向用例及清理通过；两类字段保存且相应守卫不变 |
| 音符普通拆合与扩展项重开 | `artifacts/feature-acceptance-1dec42d402a5/summary.json` | 定向探针及清理通过；生成点不等于已证明任意扩展迁移 |
| 0.13.0 独立 stdio 生命周期 | `artifacts/mcp-smoke-051e87aed535.json` | 37 工具；创建、编辑、保存、重开通过，前台句柄不变 |
| 旧版空操作脏状态与扩展时间/音高守卫 | `artifacts/feature-acceptance-101ad64d1010/summary.json`、`artifacts/feature-acceptance-3a0d2e3fcd45/summary.json`、`artifacts/feature-acceptance-63223b91968a/summary.json` | 旧版空操作错误置脏；扩展时间及音高项被守卫拦截，均保留失败基线 |
| 音高边界、纯元数据/资源合并及相关回归 | `artifacts/feature-acceptance-b07ec74aa41d/summary.json` | 5 个功能用例及清理共 6 通过，无自有前台切换或遗留会话 |
| 扩展目标、冲突、空操作与最高速度 | `artifacts/feature-acceptance-fc6a72130b1c/summary.json` | 定向用例及清理通过；同时验证旧历史和源保护 |
| 0.12.0 独立 stdio 与生命周期 | `artifacts/stdio-v0120-status-d5e0884e5809.json`、`artifacts/mcp-smoke-4d27c828d657.json` | 37 工具、0 会话；创建、编辑、保存、重开通过，前台句柄不变 |
| 原生时间与音高边界探针 | `artifacts/timeline-identity-probe-81519e73308a.json`、`artifacts/pitch-clear-native-08cb8e42a1df.json` | 观察到时间边界生成事件和音高清除原生闭区间；扩展时间映射仍未开放 |
| 带归档元数据的素材属性更新 | `artifacts/feature-acceptance-720b23a039dd/summary.json` | 旧守卫拦截，清理通过；自动审查未批准解除守卫 |
| AI 素材未知字段、身份与旧历史 | `artifacts/feature-acceptance-39ed0d000904/summary.json` | 定向用例及清理通过；覆盖源/目标、伪造字段、冲突、controller/audio 守卫和历史 |
| 扩展工程静音传输 | `artifacts/feature-acceptance-6667cde9784c/preservation.archive_transport.json` | 通过；同批素材测试失败，后来单独修复并复验 |
| 普通工程效果器历史及关联回归 | `artifacts/feature-acceptance-f97d35cd5451/summary.json` | 7 通过、2 失败，含清理；效果器历史、普通传输、样式和普通音频通过；两项失败分别在后续回执修正 |
| 普通时间编辑及扩展时间守卫 | `artifacts/feature-acceptance-a59c6e1025a7/summary.json`、`artifacts/feature-acceptance-46720e1ebe0a/summary.json` | 各定向用例及清理通过；扩展时间编辑仍未开放 |
| 素材导入诊断 | `artifacts/feature-acceptance-654debaa0a3d/summary.json`、`artifacts/feature-acceptance-f40c1dde7fe1/probe.part_create.json` | 普通/克隆对照与原生片段创建探针；素材旧失败保留 |
| 上轮控制器边界与独立素材、离线音频 | `artifacts/feature-acceptance-6cc1fd525f8e/summary.json` | 4 个功能用例及清理通过 |
| 上轮普通音频导入/编辑历史 | `artifacts/feature-acceptance-eb4111329c4f/summary.json` | 定向用例及清理通过 |
| 上轮控制器跨工程守卫基线 | `artifacts/feature-acceptance-abb8ef4a6120/summary.json` | 现有守卫拦截；不是功能通过 |

更早的逐批回执和失败记录见 [会话索引](docs/session-log/README.md)，不把不同批次相加为完整套件结果。
0.2.1 的真实 PPSF3（190 音符、80 BPM、4/4）及显式选声后的 99.5 秒非零 WAV、Robot 和其他表现证据见 [会话 07](docs/session-log/session-07.md)。其长音频旧 case 的 30 秒读取上限失败记录仍保留，独立流式检查通过，不重写历史结果。

## 保留边界

1. **声库选择**：用户明确仅用 AI 声库，不安装经典试用。此前本机 Dse=0、Dnn=21；旧经典文件继续受到源文件与身份完整性保护，经典发声和往返不作为本轮 AI 声库的验收结论。
2. **未知数据**：受测 AI 实体扩展时间编辑和同音符 `directPitches` 项扩展编辑已实现；带 tempo/拍号/controller/音频或音高项扩展的时间编辑、音高项扩展的复制拆合/跨工程/素材捕获，以及其他非实体数组、缺失父对象和部分原始写调用仍受保护。受测纯元数据及不透明资源合并已有历史支持，tempo/拍号扩展在无原生暂存变更时仍保留限制。已测音频资源迁移仅覆盖有限组合，工程级不透明资源不等于原生音频归属。解除控制器跨工程迁移及扩展音频写入保护的补丁被自动审查拦截，原因是对应事务尚缺原生验收，可能丢失扩展字段或损坏历史。带归档元数据的素材属性更新守卫解除也被自动审查拦截，原因是缺少扩展素材端到端验证，可能丢失元数据；上述守卫保留。扩展剪贴板、工程合并及 MIDI 素材导入使用独立候选预检；其他编辑路径仍可能在保存时发现同形歧义，详见 [工程保留说明](docs/project-preservation.md)。没有把此范围称作任意 VPR 无损编辑。
3. **设备与宿主**：传输验证使用一台 DirectSound 设备并静音；虚拟 MIDI 驱动的独立输入已验，物理 MIDI 采集、真实设备丢失及驱动错误通知、实际听音质量和 DAW 同步仍未完成验收。插件已观察到固定命名管道路径，[IPC 隔离调查](docs/daw-ipc.md) 尚未证明独立宿主隔离；编辑器不具备波形录音功能，见 [音频录制与宿主边界](docs/audio-recording.md)。
4. **采样率**：声乐内部合成明确要求 44100 Hz；输出混缩率独立。静态分支与 48 kHz 失败一致，但其他原生内部路径与 96 kHz 动态合成未证实。
5. **客户端**：新 stdio 连接已验证 0.13.0 原生改动；本对话连接发现 37 个工具，但本轮 `vocaloid_status` 的 Python MCP 版本仍为 0.4.0，运行中的原生宿主此前与 0.5.0 构建一致；0.13.0 原生改动需新连接载入。可见的 app-server 全局 reload 没有线程或服务选择参数，可能涉及其他已加载会话，未执行。未重启客户端或用户编辑器。

当前模块状态见 [功能矩阵](docs/feature-matrix.md)、[会话 18](docs/session-log/session-18.md) 和 [TODO](TODO.md)。
