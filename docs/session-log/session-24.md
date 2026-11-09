# 会话 24：文件事件字段与轨道 no-op

日期：2026-11-10。起点提交：`4159a50fa1c3651e30946797f302b62735163a6a`。源码版本 0.17.2；完整目标继续进行。

## 文件级事件字段

`score_tempo` 此前把首个速度事件当作新 tick 的原型，`score_curve` 则把首个控制事件复制到所有替换 tick。带不同合成未知字段的 AI 工程在 `artifacts/feature-acceptance-da5678235623/summary.json` 中复现两个错误：新速度事件继承首事件标记，保留及新控制事件也错误继承首事件标记；两个功能用例失败、清理通过。

`vocaloid_bridge/projects.py` 现在采用明确的文件级 tick 策略：保留位置携带该位置原字段，删除位置丢弃字段，新位置不继承其他事件字段；输入中重复源位置在创建输出前拒绝。`tools/check_file_event_identity_24.py` 检查不同标记、更新/删除/插入、重复位置拒绝、源文件及原生打开保存。该策略不是原生指针身份或原生历史；未改变控制器跨工程及普通编辑等受审查守卫。

## 轨道 no-op

保存并重开的普通 AI 工程中，仅用相同名称调用 `track.update` 在旧宿主上错误置脏而不改变历史；真实 MCP 红基线为 `artifacts/feature-acceptance-410a03ae2d30/summary.json`，清理通过。`native/ScoreOperations.cs` 对仅包含相同名称的请求，在确认原生无暂存编辑后直接返回轨道摘要，保持既有 clean/dirty 状态；没有概括其他字段或混合 no-op。新验收检查真正改名保存重开和存在暂存 tempo 时的拒绝，见 `docs/score-noop-24.md`。

## 其他有限探针

三个 `gpt-6.1-terra` 子 agent 分别调查主音量时间边界、普通素材事务和轨道 no-op。`artifacts/master24-missing.json` 和 `artifacts/master24-adjacent.json` 观察两组边界、插入/删除及两种 tempo 选项中的主音量生成/迁移和成功操作后的显式 rollback/undo/redo；未证明原生内部失败恢复或未知字段往返。`artifacts/media-transaction-24-e9c72d5172d0/receipt.json` 中范围锁外的竞争写入成功而替换失败；未建立持续排他提交或原生刷新协议。受审查的占用拍号、轨道/controller 普通编辑、音高删除、controller 跨工程、扩展音频和归档素材守卫未更改，见 `docs/master-timeline-24.md` 和 `docs/media-transaction-24.md`。

静态检查发现文件级 `score_replace_notes` 仍以首音符为原型，可能复制其未知字段；本轮未对该路径作动态证明或改动，涉及 `directPitches` 须继续遵守原审查边界。普通素材 `media_update` 的未知字段丢失仍未解决。

## 验证与客户端

构建前 Roslyn 语义检查覆盖 26 个 C# 源文件、生成的全局 using 文件及 208 个引用，Python AST 覆盖 82 个文件，操作目录检查通过；唯一一次 Release 构建为 0 警告、0 错误。`artifacts/feature-acceptance-f4c4b6029e12/summary.json` 为 9 个功能用例及清理共 10 通过，含文件事件、轨道 no-op、普通轨道、工程生命周期和原有守卫，无自有前台切换或遗留会话。更新 MCP 工具说明后的文件事件两项及清理在 `artifacts/feature-acceptance-6615c4d86e30/summary.json` 复验通过，不与前一批次计数相加。独立 stdio 生命周期用例报告 0.17.2；本对话现有连接仍报告 Python MCP 0.4.0、0 会话，原生宿主此前比对为 0.5.0；全局刷新未执行。

后续继续文件级音符原型风险、普通素材事务和已拦截守卫的单项证据/审批，以及主音量时间、物理 MIDI、DAW 隔离和作用域合适的客户端重连。
