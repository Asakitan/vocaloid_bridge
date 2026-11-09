# 会话 09：AI 工程默认值、扩展数据与实时输入

日期：2026-11-10。起点提交：`5fa8b40`。本轮交付 0.4.0；总目标继续进行。

## 目标与分工

用户确认只用 VOCALOID:AI 版本，经典试用保持未安装；保留已有工程源文件保护。主线核对 AI 创建默认值和生命周期，子 agent 分别处理扩展数据复制、MIDI 输入和音频输入/宿主连接。全部原生工作仍使用私有后台，不接管用户编辑器。

## 现状

本轮在保留创建、打开、编辑、保存的基础上增加到 37 工具及 125 个操作。未知实体字段的分割/连接、硬件 MIDI 输入和 DAW 路径仍有待完成的边界。

`artifacts/feature-acceptance-373066efb83d/summary.json` 复现未指定轨道类型时创建传统 MIDI 轨，与用户 AI-only 选择不一致。当前修改将无类型参数的默认轨道改为 `MidiAi`，显式 `Midi` 参数仍保持原有语义；新片段声库仍需调用者明确选择。`artifacts/feature-acceptance-32f1c9da5151/summary.json` 验证空工程、默认 AI 轨、显式选声、编辑、保存重开和原生合成，2 项通过含清理；构建 0 警告、0 错误。

已核对并明确 `project_import` 的 `prefer_ai` 仅传给原生 MIDI/SMF/VSQ 载入器；VPR、VSQX 和 PPSF 不经该参数转换，调用也不自动替换声库。

整合构建为 0 警告、0 错误；`artifacts/feature-acceptance-647c107fc2bd/summary.json` 中扩展复制及历史通过，但 MIDI 设备枚举在安装版封装的 UserDirectories DLL 搜索路径上遇到 `DllNotFoundException: winmm.dll`。随后改用 System32 明确解析同一 WinMM 枚举接口并复验，原失败回执保留。

为避免逐错构建，先用已构建宿主跳过故障枚举运行其余路径：`artifacts/midi-synthetic-01c0cf295993.json` 的显式事件、力度、保持音闭合、错误批次、跨速度变化、保存重开与静音 transport 同步均通过；此诊断未打开 MIDI 设备，也未验证枚举修复。

WinMM 解析修正后统一构建为 0 警告、0 错误；`artifacts/feature-acceptance-878d0c135692/summary.json` 的 MIDI 六操作及清理为 2 通过，`artifacts/midi-synthetic-3fa675486b20.json` 的事件流、跨速度变化和显式静音 transport 同步通过。枚举到两条 CubaseAI 端口，未打开 MIDI 设备；事件流结果不代表硬件采集通过。当前 WinMM `MIM_ERROR` 通知未报告，需在硬件录制验收前处理。

`artifacts/feature-acceptance-647c107fc2bd/preservation.duplicates.json` 验证带扩展字段的轨道、片段、音符复制及历史、同形异数据拒绝与源关闭后克隆。非空右半片段的原生拆合观察 `artifacts/preservation-part-split-15fd889b4936.json` 显示子音符会换身份，拆合暂保留保护限制。

官方 FAQ 和本机静态接口核对确认编辑器不具备波形录音，DAW 录制后的 WAV 可导入。VST3 命名 IPC 隔离尚未证明，本轮未加载插件或操作用户前台。细节见 `docs/audio-recording.md`。本对话旧 `vocaloid6-native` 连接实测返回 `Transport closed`，独立新 stdio 测试已通过；客户端重新连接后才能发现新版工具。
