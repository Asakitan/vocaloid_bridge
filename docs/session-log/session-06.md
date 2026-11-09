# 会话 06：原生功能收口与调用契约

日期：2026-11-10。

## 目标

保留项目创建、打开、编辑、保存闭环，补齐后台功能的操作入口和验证证据。执行路径固定为私有 Windows desktop 中的原生引擎，不接管用户交互编辑器。

## 实施范围

- 传统格式身份往返、资源复制。
- 精细乐谱、表现与时间换算。
- 内置音频效果和混缩格式。
- 素材的特殊表现、操作发现及文档契约。

## 验证

整合回执 `artifacts/feature-acceptance-012574702338/summary.json`：76 通过、5 失败、2 个缺样本项。36 个工具和 108 个操作有成功调用；没有传输错误或遗留会话。单次成功调用不代表完整语义验收。

后续 `artifacts/feature-acceptance-6d7fb89e808b/summary.json` 修正了裁剪静音尾段的测试输入，并确认经典 Singing Skill 在重开后因轨道变 AI 被正确拒绝。Robot 参数往返但实际 PCM 无变化，Lua 返回 `NoError`；最新单项 `artifacts/feature-acceptance-7085da10d352/summary.json` 仍失败。PPSF V2、VSQX3/4 的经典身份丢失，PPSF V3 缺真实样本。未将目标标为完成。

## 已落实修复

- 原生数据库前置初始化，修复直接音频导入后的克隆空轨；`artifacts/feature-acceptance-caccb6a49ed7/summary.json`。
- 每宿主独立 VSM cache namespace；固定名称的双宿主删除问题在 `artifacts/host-isolation-22aebb82b8c7.json` 复现，`artifacts/host-isolation-732451efccb9.json` 验证修复。
- Windows DLL 锁定通过私有构建快照解决，不结束用户客户端；仅结束了本轮创建、已确认 0 会话的旧测试宿主。
- 原生 VSStyle 捕获使用 VEM ToPlain，避免将归一化浮点当作样式整数；HMM 权重填回原生素材既有标准字段。`artifacts/feature-acceptance-09a5d49126c6/summary.json` 通过。
- 108 个操作目录由源 dispatch 和 Markdown 自动生成；完整验收中的 `remaining.operation_catalog` 校验实际 MCP。
- 批量音符、非空颤音、真实 staged 回滚、音素位置、采样率与 bus 保存重开通过；音符时序重开需渲染后读回，record-arm 为会话态。原生深测转录与完整 MCP 的 `remaining.score_dispatch` 相互区分记录。

## 接续

继续处理经典格式身份与 Robot，不增加前台执行或替代后端。先核查 native OpenSequence 外的初始化契约、VLC 与 VSM app ID 的关联；现有证据尚未确认 Robot 失败根因。旧共享缓存会相互删除，后续调查须保留已实现的隔离约束。
