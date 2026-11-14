# Session 47: 音符、样式与原生数据保护

日期：2026-11-13。

## 目标

检查 VOCALOID6/7 MCP 是否遗漏常用操作或存在实际编辑缺陷，针对可复现的问题修复，并区分已验证范围与原生能力限制。验收使用自建工程、私有桌面和独立 stdio MCP，不操作用户编辑器或覆盖原始工程。

## 修改

- `vocaloid_features` 的音符功能补齐新增、更新、删除、清空、复制、拆合和批量编辑模板。`project_inspect(feature="notes")` 绑定目标索引；结构编辑后应重新读取索引。底层 `note.remove` 和 `note.clear` 已存在，并非删除实现缺失。
- 样式效果使用原生 `PrepareForUse` 初始化控制器，再先应用模式参数和其余参数。V6 片段效果读取保存的 `WPartEffectBlock` 参数及模式相关范围，避免共享控制器默认值冒充项目值。离线音频动作和效果作用域按产品标注支持情况。
- V6/V7 原生 AI DVQM 写入会影响音符 Singing Skill 表示，撤销无法可靠恢复权重、时长或保护状态。结构化入口拒绝 AI `dvqm_set` 和非空 `dvqm_clear`；已有选择仍可读取，空清除可作为空操作。V7 `S5Attack` 是独立 AI 声库参数，不是 DVQM。
- 有既存 Attack/Release 的 AI 音符拒绝 `note_skill_set/reset`；高级 `project_call` 也拒绝相应的 DVQM setters/reset 与 note skill setters/reset。普通音符和经典声部不因这一条件被禁止。
- 扩展工程的 note skill set/reset 进入既有归档实体、历史与资源保护。目标 `singingSkill` 或 `dvqm` 子树含未知字段时拒绝；受测其他音符、音高、控制器、轨道自动化与 ZIP 资源保留。
- 验收代码修正 V6/V7 作用域、VoiceType/Take 字段、跨片段时间插入及不支持的 VMM 情况；历史用例与产品证据不混计。

## 验证

- V6 6.13.3.1 与 V7 7.0.0.1：各自 35 个原生源文件、218 个引用的语义预检均为 0 错误；两个产品通过 `tools/setup.ps1` 的隔离 Release 构建。
- V7 音符删除/清空及发现模板、AI DVQM 写入保护、note skill 修改/撤销/重开、`asa Warm Chorus` 参数与模式、`asa Retro (V7)` Phaser、`asa Lead Vocal (V7)` Reverb、保存重开及撤销：5 个用例和清理通过，`artifacts/feature-acceptance-0e95b9aeeed5/summary.json`。
- V6 音符编辑/删除、全部公开 DVQM 反射写入口保护及 Chorus 模式和片段参数读回：3 个用例和清理通过，`artifacts/feature-acceptance-dbcc3e8024fd/summary.json`。
- 带未知字段工程的 note skill set/reset、undo/redo、保存重开、冲突拒绝及直接反射保护：V7 `artifacts/feature-acceptance-45e983f01064/summary.json`、V6 `artifacts/feature-acceptance-e449e555e781/summary.json`，各为功能用例与清理通过。
- 效果查询前后比较序列化工程、脏状态与撤销历史：V6 `artifacts/feature-acceptance-9e59fd35aaf4/summary.json`、V7 `artifacts/feature-acceptance-e725bd16f983/summary.json` 均通过；该项未比较音频 PCM。
- V7 使用实际原生合成的人声作为输入，双轨 44.1 kHz 立体声主混缩与分轨求和比较通过；192 kHz 单声道主效果与旁路结果有实际 PCM 差异，分轨不含主效果。两个用例及清理通过，`artifacts/feature-acceptance-4c197f2d178a/summary.json`。
- V6 使用独立构造的已有 AI DVQM 素材夹具验证读回与往返：`artifacts/feature-acceptance-26650fbeeb36/summary.json`。V7 没有对应 VMM 后端，不将 V6 结果记为 V7 通过。
- 未修复前的高级反射旁路实际允许 AI `WIVSMDvqm.Set`，失败回执 `artifacts/feature-acceptance-3859f1b8ab63/summary.json`；修复后逐项拒绝公开写方法并验证音符权重和历史不变。
- 操作索引由源分发和文档契约生成，71/16/32/5/6 项，`tools/generate_operation_catalog.py --check` 通过。

## 边界

AI DVQM 的无损写入在本次会话尚未实现；当时明确拒绝而不是修复原生引擎。V7 VMM、片段效果和变声仍不支持；会话 48 新增 PCM/浮点 WAV 的桥接反转。未运行本次全量 130 操作套件，未覆盖所有预设、所有未知字段组合、物理设备、DAW 或主观听音。当前聊天未暴露 VOCALOID MCP 工具；独立 stdio 验收不证明客户端已重连新宿主。现有客户端须先保存并关闭工程，再重新连接 `vocaloid6-native`。