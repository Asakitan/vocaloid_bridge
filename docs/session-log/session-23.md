# 会话 23：操作契约与碰撞审查

日期：2026-11-10。起点提交：`a6f8f3c370f54dbe27f98d58c4ad6ff0d6efad19`。源码版本 0.17.1；完整目标继续进行。

## 操作目录修复

原提交的 `operations.json` 中有 18 个结构化操作的 `contract_rows` 为空：乐谱 13 个、剪贴板 5 个。原生 dispatch 及相应文档逐项核对后，在 `docs/score-operations.md` 与 `docs/native-protocol.md` 添加精确操作契约，包括剪贴板选择器默认值。`tools/generate_operation_catalog.py` 只匹配 Markdown 操作首列，任一 dispatch 操作缺少对应契约时报告错误；重新生成后的 125 项均有契约。之后复核发现既有非空行也有将选择器或默认参数留在正文的情况，因此同时补充音符、控制器、声库、选择、音频、素材和剪贴板契约行。`tools/check_library_remaining.py` 验证所有行与实际 MCP 返回一致，并对乐谱、音频、素材及剪贴板共八项单独查询核对关键字段。目录完整是发现证据，不等于任意功能组合均已验收。

独立私有 stdio 的 `artifacts/feature-acceptance-95209afa6b83/summary.json` 包含 3 个功能用例及清理共 4 通过：目录、私有剪贴板五操作和创建/编辑/保存/重开；生命周期用例报告 MCP 0.17.1，无自有前台切换或遗留会话。修正剪贴板默认参数后，`artifacts/feature-acceptance-ddb153c0f492/summary.json` 的目录用例及清理通过；补齐其他公共选择器后的最终复验见 `artifacts/feature-acceptance-dba5e14102fe/summary.json`。未把定向计数相加，也未重跑历史完整套件。本轮没有 C# 生产代码变化或 Release 构建。

提交前 Python AST 检查覆盖 79 个文件，操作目录检查通过；已核对受审查的原生守卫文件没有差异。

## 原生探针与审查

三个 `gpt-6.1-terra` 子 agent 分别研究占用拍号边界、主音量时间编辑和素材文件共享；均使用自有合成夹具及工作区路径，未操作交互编辑器、已有 DAW/MIDI 或经典试用。

`artifacts/timeline-identity-probe-eee54488979d.json` 中普通 AI 工程的占用拍号边界显示原 bar-2 对象保留指针并更新值，bar-3 删除，bar-4 对象移位；显式 rollback/undo/redo 恢复对应身份。`artifacts/feature-acceptance-7e646bbd736f/summary.json` 是带不同未知字段预期正例在第一步被现有守卫拒绝的红基线，后续历史、重开及第二个 tempo 选项未执行。自动审查拦截了占用边界守卫的生产映射补丁：未知字段往返和原生失败回滚缺少证明，可能丢失元数据，并需针对该守卫单项批准。补丁未应用，守卫保持原位，见 `docs/meter-collision-23.md`。

`artifacts/master23-probe-c9e1fe80edaa.json` 观察到主音量时间插入/删除的受测原有及生成点身份，并观察成功暂存后的显式 rollback 与 undo/redo；生成点插值、其他边界、未知字段往返与原生失败未验，主音量时间守卫未改变，见 `docs/master-timeline-23.md`。

`artifacts/media-atomic-23-dbc4a1ee15e6/receipt.json` 使用合成文件和独立子进程，观察两种共享模式持锁时写入及替换失败、释放后替换成功；探针现限制子进程路径只能指向同一自有合成目录。该受控交错未证明覆盖检查到提交的竞争隔离，也未执行新的原生刷新；普通素材属性未知字段丢失仍存在，见 `docs/media-atomic-23.md`。此前轨道自动化/controller 普通编辑、音高删除、controller 跨工程、扩展音频及归档素材属性的审查守卫保持原位。

## 客户端与后续

本对话连接本轮仍报告 Python MCP 0.4.0、0 会话，其原生宿主此前比对为 0.5.0；独立 stdio 的生命周期用例报告 0.17.1。全局刷新缺少线程/服务选择且可能影响其他会话，本轮未执行。用户选择只用 AI 声库，未安装经典试用。

后续需已拦截守卫的针对性证据和单项审批、普通素材完整事务及缓存恢复、主音量和其他扩展时间组合、物理 MIDI、真实 DAW 隔离和作用域合适的客户端重连。
