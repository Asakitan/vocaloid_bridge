# 当前状态

日期：2026-11-10。版本：0.2.0。目标继续进行；完整功能验收尚未完成。

## 已实现与实测

- 36 个 MCP 工具，64 个乐谱、9 个音频、30 个素材、5 个剪贴板操作，共 108 个；`vocaloid_operations` 提供操作名与文档契约。
- 保留原生创建、打开、编辑、保存、关闭闭环，源工程独立保护；仅使用私有 Windows desktop，无 UI 或其他音源回退。
- 新增批量音符、音素时序、颤音曲线、时间换算、暂存回滚、总线/录音标志及采样率入口；非空曲线、时序读写与保存重开有实测。
- 新增私有样式捕获/覆盖/属性编辑/删除，Singing Skill 和音符 HMM 权重；素材标准字段写出修复后，HMM 权重捕获、导入、保存重开通过。
- 原生数据库前置初始化修复直接导入音频后的克隆丢轨；源关闭后克隆原始/处理音频独立导出通过。
- 每宿主独有 VSM 缓存命名空间，修复另一宿主关闭时删掉当前 WAV 的问题；DLL 从私有构建副本运行，避免活动宿主锁住构建输出。
- 11 个内置效果的受测参数、可用预设、旁路、保存重开及实际混缩有通过证据；48/96 kHz 和双边界通过。不代表所有预设和所有听感组合已验。

## 验证与明确缺口

构建：0 警告、0 错误。整合回执 `artifacts/feature-acceptance-012574702338/summary.json`：76 通过、5 失败、2 个缺样本项；36 个工具及 108 个操作均出现过成功调用，不将单次调用等同完整语义验收。

后续定向回执 `artifacts/feature-acceptance-6d7fb89e808b/summary.json` 修正了裁剪到静音尾段的测试假设，48/96 kHz 通过；严格检查同时确认经典 Singing Skill 重开受经典轨道变 AI 的问题影响。当前主要待修复项为：

1. PPSF V2、VSQX3/4 经典轨道和声库身份保存重开丢失；经典 Singing Skill 重开同受影响。本机仅枚举到 21 个 Dnn 声库，但尚未证明缺经典声库就是根因。
2. Robot 启用前后 PCM 相同，原生 Lua 返回 `NoError`，没有声音差异验收通过；最新回执 `artifacts/feature-acceptance-7085da10d352/summary.json`。
3. PPSF V3 缺真实样本；两个缺样本用例均指向此输入。
4. 设备播放、实时录制、DAW、用户界面和全局偏好不是本轮已验能力；变更采样率/总线后的组合渲染仍有未解失败。

录音标志属于会话状态，重开恢复关闭；音素时序重开后需原生渲染生成可读位置。功能边界以 `docs/feature-matrix.md` 为准。

## 关键证据

- 并发缓存：修复前 `artifacts/host-isolation-22aebb82b8c7.json`；修复后 `artifacts/host-isolation-732451efccb9.json`。
- 私有样式和 HMM：`artifacts/feature-acceptance-09a5d49126c6/summary.json`。
- 音频克隆：`artifacts/feature-acceptance-caccb6a49ed7/summary.json`。
- 乐谱深测转录：`artifacts/score-deep-receipt-28484b82a63a.json`、`artifacts/score-followup-receipt-208cabf8d914.json`；真实 MCP 调度见整合回执中的 `remaining.score_dispatch`。
- 客户端重新加载 `vocaloid6-native` 后发现新增工具和新宿主；本轮未重启用户客户端或编辑器。

历史基线见 `docs/session-log/session-05.md`；本轮记录见 `docs/session-log/session-06.md`。旧 60/1 与 45/45 记录不代表当前全部功能已通过。
