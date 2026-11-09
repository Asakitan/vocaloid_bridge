# 会话 21：轨道自动化项与时间删除

日期：2026-11-10。起点提交：`ad0698ab0a2379dbbac19985d34316e4981deefd`。源码版本 0.16.0；完整目标继续进行。

## 范围与实现

仅使用 VOCALOID:AI 声库、合成工作区夹具和私有后台原生会话；未安装经典试用，也未操作用户编辑器或已有 DAW/MIDI 端点。三个 `gpt-6.1-terra` 子 agent 分别研究普通素材属性事务、音高项删除与轨道自动化扩展；主线核对实现和受审查边界，新增时间删除映射并统一验收。

`ProjectArchiveTrackAutomation.cs` 将轨道音量和声像项未知字段绑定原生轨道及完整点集：同 tick 更新保留字段，删除点丢弃字段，新点不继承字段。轨道属性/重排、原生历史、保存和重开经过定向验证；删除、复制、时间编辑、剪贴板及跨工程等未验证路径保留守卫。旧宿主红基线为 `artifacts/feature-acceptance-79945951763e/summary.json`。

`ProjectArchiveTimeline.cs` 按安装版托管 `DeleteTime` 的受测规则映射被删除与保留的 tempo/拍号事件；新生成 tempo 边界不继承未知字段。不同拍号的生成边界和初始 tempo 删除受保护。普通拍号探针为 `artifacts/feature-acceptance-467a9a7eaeab/summary.json`；旧宿主拒绝预期扩展删除的红基线为 `artifacts/feature-acceptance-cfe62cee3296/summary.json`。原生 Move 内部及其他碰撞、边界组合不在本轮证明范围，见 `docs/timeline-delete-21.md`。

## 审查与素材边界

四个音高项删除预期正例在 `artifacts/feature-acceptance-830a85e95c28/summary.json` 被既有守卫拦截；其后续断言未执行。自动审查拦截了单独解除守卫的请求，因为目标绑定删除钩子尚未集成，可能丢失元数据。候选保存在被忽略的 `.runtime/note-delete-candidate-21.cs`，未集成、未编译、未验证；本轮守卫回归确认四个路径仍在修改前拒绝。此前控制器跨工程、扩展音频写入及带归档元数据素材属性守卫保持不变。

`artifacts/feature-acceptance-25f45d337d42/summary.json` 再次复现普通素材 `media_update` 丢失顶层和 `part` 合成未知字段；生产行为未变。独立进程探针 `artifacts/feature-acceptance-2ca7dc2676b2/summary.json` 手工恢复已知夹具的嵌套/数组标记并检测一次提交前外部改写；该检查与替换之间仍存在竞争，通用身份、刷新失败和崩溃恢复未验，见 `docs/media-property-21.md`。

## 验证

构建前 Roslyn 语义检查覆盖 29 个 C# 文件和 208 个引用，Python AST 覆盖 72 个文件，操作目录检查通过；一次 Release 构建为 0 警告、0 错误。之后新增的守卫回归及注册文件另通过 Python AST 检查。

`artifacts/feature-acceptance-e8eb9b6496cb/summary.json` 为 16 个功能用例和清理共 17 通过，包含时间删除、轨道音量/声像项、主音量混合、现有控制器及音高守卫、创建保存重开；无自有前台切换或遗留会话。未重跑完整历史套件，旧红基线单独保留。

`artifacts/mcp-smoke-acbdb340d53d.json` 的新独立 stdio 连接报告 0.16.0、37 个工具，创建、编辑、保存、重开及音符往返通过，前台句柄不变。本对话现有连接仍报告 Python MCP 0.4.0、0 会话；其原生宿主此前比对为 0.5.0。全局刷新没有线程/服务选择，未执行。

后续需普通素材完整事务、音高项删除经验证的目标钩子及单项审批、不同拍号边界和其他扩展组合、物理 MIDI、真实 DAW 隔离与现有客户端定向重连。
