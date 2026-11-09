# 会话 22：拍号生成边界与扩展编辑审查

日期：2026-11-10。起点提交：`901c5413e84f9f9dc2679933e9ed6a3a2732c38f`。源码版本 0.17.0；完整目标继续进行。

## 范围与实现

仅使用 VOCALOID:AI 声库、合成工作区夹具和私有后台原生会话；未安装经典试用，未操作用户编辑器或已有 DAW/MIDI 端点。三个 `gpt-6.1-terra` 子 agent 分别调查不同拍号生成边界、轨道自动化扩展普通编辑和素材刷新；主线核查代码、补充控制器普通编辑红基线并统一验收。

`ProjectArchiveTimeline.cs` 新增不同拍号且开始小节尚无拍号事件时的受测生成边界映射：生成项不继承未知字段，已删除项丢弃字段，其他项按原生身份迁移。原生托管方法在删除和移动前插入边界；两个 tempo 选项的私有身份探针显示受测新对象与所有原始对象不同，保留对象稳定，rollback/undo/redo 返回相应状态。`tools/run_timeline_identity_probe.py` 和 PowerShell 探针已参数化，复现回执为 `artifacts/timeline-identity-probe-47ef55371dd5.json`。生成项在首次暂存和回滚后第二次提交时可有不同指针；不能把两次分配视为同一对象。开始小节已有事件的碰撞仍受保护。旧宿主红基线为 `artifacts/feature-acceptance-336f60d13d89/summary.json`。

## 扩展编辑审查与素材事务

轨道自动化扩展的八个普通编辑预期正例在 `artifacts/feature-acceptance-dd354933659d/summary.json` 全部被旧守卫拦截；此前 `artifacts/feature-acceptance-ef256eebecdd/summary.json` 是缺 `lang_id` 的夹具准备失败。控制器扩展普通音符编辑在 `artifacts/feature-acceptance-72bcbfa55a05/summary.json` 被守卫拦截，后续断言未执行。自动审查拦截了组合放宽补丁，因为原生身份与失败回滚证据不足，可能静默丢失元数据；未应用该补丁，相关守卫保持原位。独立红基线脚本不注册为发布通过用例，见 `docs/track-edits-22.md` 和 `docs/controller-notes-22.md`。此前音高删除、控制器跨工程、扩展音频写入与带归档素材更新的审查边界也保持原位。

`artifacts/media-failure-22-045a23ff9013/receipt.json` 的独立进程夹具观察到检查后外部写入在替换时被覆盖。独占锁使独立读取实际得到 `PermissionError`；原生 `ReadAllClipFiles()` 返回成功枚举值但未枚举该素材，旧引用名称为空。解锁重刷后新枚举恢复，旧引用仍未恢复；这不是原生非成功返回、完整缓存恢复或崩溃持久性证明。进程 `close()` 返回但未单独枚举退出状态。生产 `media_update` 的普通素材未知字段丢失仍存在，见 `docs/media-failure-22.md`。

## 验证

构建前 Roslyn 语义检查覆盖 26 个 C# 源文件和生成全局 using 文件及 208 个引用，Python AST 覆盖 76 个文件，操作目录检查通过；唯一一次 Release 构建为 0 警告、0 错误。

提交前 Python AST 覆盖 77 个文件，PowerShell 语法与操作目录检查通过。守卫文件差异检查的首条 PowerShell 包装条件误把无输出的 `git diff --quiet` 当作 false；使用 `$LASTEXITCODE` 复核为 0，相关守卫文件实际没有差异。

`artifacts/feature-acceptance-80b1c4779514/summary.json` 为 12 个功能用例及清理共 13 通过，覆盖两个 tempo 选项下生成拍号及字段/历史、占用位置碰撞守卫、旧时间线回归、控制器/轨道自动化/音高守卫和生命周期；无自有前台切换或遗留会话。未重跑完整历史套件。

`artifacts/mcp-smoke-cf2c42db8233.json` 的新独立 stdio 连接报告 0.17.0、37 个工具，创建、编辑、保存、重开及音符往返通过，前台句柄不变。本对话连接本轮仍报告 Python MCP 0.4.0、0 会话；其原生宿主此前比对为 0.5.0。全局刷新没有线程/服务选择，未执行。

后续需已拦截守卫的原生身份/回滚证据与单项审批、普通素材完整事务、拍号碰撞和其他扩展组合、物理 MIDI、真实 DAW 隔离与现有客户端定向重连。
