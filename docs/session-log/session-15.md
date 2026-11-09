# 会话 15：控制器拆合、独立素材与音频历史

日期：2026-11-10。起点提交：`b247fdb`。本轮源码版本 0.10.0；总目标继续进行。

## 目标与分工

继续只使用 VOCALOID:AI 声库和后台私有原生会话，不安装经典试用，不接管用户编辑器或连接现有 DAW/MIDI 端点。子 agent 分别处理控制器扩展跨工程传输、工程内复制拆合和音频事务；主线审阅整合、实现独立私有素材操作及离线音频的受控调用。

## 修改与证据

`ProjectArchivePreservation.cs`、`ScoreOperations.cs` 和 `EngineSession.cs` 将控制器事件扩展迁移到受测轨道/片段副本及拆合结果，按片段身份、控制器类型和绝对 tick 映射，提交前校验原生曲线。原生引擎拆分时可能生成边界点：`artifacts/feature-acceptance-c5699ce5886f/` 观察到在 480 tick 拆分时右侧生成值为 40 的新点，重合后仍有该原生点；桥接层不把旧未知字段附给新点。带控制器扩展的重叠身份产生冲突时回滚；没有控制器扩展的普通曲线继续遵循原生结果。

首轮 `artifacts/feature-acceptance-a4ff744bd605/summary.json` 为 10 项通过、1 项失败，失败是生成边界点被误当作身份冲突。修正后 `artifacts/feature-acceptance-6d389ad715a5/summary.json` 的 4 个功能用例及清理通过；进一步的边界事件、同形轨道复制、重叠冲突和原生普通曲线回归在 `artifacts/feature-acceptance-6cc1fd525f8e/summary.json` 通过。原失败回执保留。

`ProjectArchiveLibrary.cs` 和 `RpcServer.cs` 允许扩展工程使用只读源工程或只修改桥接自有目录的样式捕获/更新/删除、素材更新/删除；若所选片段及其音符没有未知归档字段，也可捕获该片段为原生媒体。若所选内容带未知片段、音符或控制器字段，捕获前报错，避免原生 VMM 素材静默丢失这些字段。测试覆盖扩展源状态和历史不变、无扩展片段捕获及导入、私有样式和素材更新删除、保存重开。旧版守卫基线为 `artifacts/feature-acceptance-a9247052cbdd/summary.json`。

`process_audio` 对显式外部 WAV 使用原生离线渲染，不改变工程序列；扩展工程的反转逐样本、输入覆盖保护及工程状态/历史检查在 `artifacts/feature-acceptance-6cc1fd525f8e/summary.json` 通过。`AudioOperations.cs` 的普通工程导入和编辑使用同一原生事务边界，`artifacts/feature-acceptance-eb4111329c4f/summary.json` 验证撤销重做及源 WAV、保存重开；普通音频素材捕获/导入回归也在前述回执中通过。旧版普通工程撤销不可用的基线为 `artifacts/feature-acceptance-e69a7251376f/summary.json`。

集中放开控制器扩展跨工程迁移和扩展工程音频写入的补丁被自动审查拦截：原因是对应跨工程/音频事务缺少原生运行验证，存在扩展字段丢失或历史损坏风险。现有守卫保留；`ProjectArchiveTransfer.cs` 中的控制器深拷贝准备代码及独立验收脚本尚未通过跨工程验收，`artifacts/feature-acceptance-abb8ef4a6120/summary.json` 记录旧版保护基线。扩展工程音频导入/编辑仍受保护，相关未通过的独立脚本没有列为发布验收项。

最终构建 0 警告、0 错误，构建前 Roslyn 语义预检覆盖 21 个 C# 文件和 211 个引用；Python AST、操作目录与 diff 检查通过。最终受测用例及清理均未记录自有宿主前台切换或遗留会话，不是完整历史套件重跑。新独立 stdio 状态 `artifacts/stdio-v0100-status-49b6ed9faee4.json` 报告 0.10.0、37 个工具及 0 会话；本对话旧连接此前报告 Python 0.4.0 和 0.5.0 原生宿主，需重新连接核对，未重启用户客户端或编辑器。

## 剩余边界

控制器扩展跨工程迁移、所选内容含未知字段的媒体捕获、扩展工程音频写入、其他非实体数组、纯元数据历史、物理 MIDI 和实际 DAW/插件隔离仍待处理。先前合成音频资源和私有快照证据不等于任意文件及长会话资源组合均已验证。
