# 会话 14：扩展工程输出、拍号合并、控制器与音频

日期：2026-11-10。起点提交：`458cf1b`。本轮源码版本 0.9.0；总目标继续进行。

## 目标与分工

继续只使用 VOCALOID:AI 声库和后台私有原生会话，不安装经典声库试用，不接管用户编辑器或连接现有 DAW/MIDI 端点。子 agent 分别实现拍号扩展合并、控制器事件扩展编辑和音频轨/片段扩展迁移；主线审阅整合，并实现带扩展工程的原生输出快照。

## 修改与证据

`ProjectArchiveOutput.cs` 和 `RpcServer.cs` 对受跟踪扩展工程的人声片段合成、MIDI 导出及离线混缩/分轨使用独立原生工程快照，保留源会话 ID、源路径保护和历史；原生宿主和引擎不变。旧版在 `artifacts/feature-acceptance-9ce5897ac9db/summary.json` 中因扩展守卫拦截 MIDI 导出。新用例验证修改后的 MIDI 音高、非零原生人声和混音、分轨、失败清理、源状态与撤销重做、未知字段及额外成员保存重开。

`ProjectArchiveTimeSigMerge.cs` 在目标的独立候选中逐事件复现安装版包装器的原生小节换算和拍号复制，记录每个源事件的目标小节，校验中间结果和实际整批结果，扩展数据随原生历史回退。合并回归覆盖替换、1920 tick 与非小节对齐的 5000 tick 偏移、同值覆盖、来源和目标扩展、撤销/重做、保存重开及源文件保护。旧版探针 `artifacts/feature-acceptance-2d1f610439e1/probe.timesig.json` 观察到非对齐偏移下前面的拍号会影响后续小节换算，不能简单套固定小节偏移。

`ProjectArchiveArrays.cs`、`ProjectArchivePreservation.cs` 和 `ScoreOperations.cs` 将控制器事件扩展绑定到原生片段、控制器类型和 tick；单点 `controller_index` 支持显式移动。受测直接编辑、碰撞、替换、删除后重建、撤销重做、克隆和重开通过；最后一个未知控制器字段删除后，其他编辑重新开放，旧历史仍保留字段。含控制器扩展的复制、拆合和跨工程传输仍在修改前受保护，同形轨道携带不同扩展时拒绝错绑。

`ProjectArchiveTransfer.cs`、`ProjectClipboard.cs` 和 `ProjectInterchange.cs` 增加音频轨及片段的实体扩展映射。合成用例使用两个不同但同名的 WAV、各自的处理后 WAV，验证轨道/片段剪切、源关闭及剪贴板清理、资源冲突、撤销重做、工程合并、保存重开和原始/处理资源逐字节导出；它不证明任意音频处理或资源组合。旧版拦截的基线为 `artifacts/feature-acceptance-c69a00d608f0/summary.json`。

集成构建为 0 警告、0 错误；构建前 Roslyn 语义预检覆盖 20 个 C# 文件和 211 个引用，Python AST 与操作目录检查通过。`artifacts/feature-acceptance-b0b2d367967f/summary.json` 为 13 个功能用例及清理共 14 项通过，未记录自有宿主前台切换或遗留会话；不是完整历史套件重跑。

主线复核时将控制器扩展纳入旧历史空快照、恢复和跟踪卸载判断，避免把含控制器扩展的状态误认为空。重新语义检查和构建通过；定向重验控制器编辑、歧义、剪贴板旧历史及清理共 4 项通过，回执 `artifacts/feature-acceptance-982ed9b70fa6/summary.json`。

新独立 stdio 状态 `artifacts/stdio-v090-status-28f3067b0802.json` 报告 0.9.0、37 工具及 0 会话。本对话现有连接此前报告 Python 0.4.0，原生宿主此前对应 0.5.0；需重新连接后核对，未重启用户客户端或编辑器。

## 剩余边界

控制器扩展的复制/拆合/跨工程迁移、其他非实体数组、更多音频资源组合、纯元数据合并历史、其他编辑的同形歧义、物理 MIDI 和实际 DAW/插件隔离仍待处理。私有资源副本和已粘贴快照目录按现有生命周期保留，长会话重复撤销分支可能累积空间。
