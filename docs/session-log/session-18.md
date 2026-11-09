# 会话 18：受限扩展时间线与音高项字段

日期：2026-11-10。起点提交：`07d8f9cded383cc73c588466e472db559bfb6555`。本轮源码版本 0.13.0；完整目标继续进行。

## 目标与分工

仅使用 VOCALOID:AI 声库及后台私有原生会话，不安装经典试用，不操作用户交互编辑器或已有 DAW/MIDI 端点。子 agent 分别研究扩展时间线事件通知、音高项数据和现有客户端重连；主线审查并整合源码、事务、守卫和定向验证。

## 修改与证据

`ProjectArchiveTimeline.cs` 和 `ScoreOperations.cs` 在受限 MIDI/AI 实体扩展工程上提供 `time.insert` / `time.delete`：先检查序列无暂存修改，再在独立原生候选上执行和序列化，实际事务的暂存及提交后核对轨、片段和音符身份与预期位置。跨 MIDI 片段边界仍按原有规则保护。包含 tempo、拍号、controller、直接音高项扩展或 Audio 轨的工程不走该路径；被自动审查拦截的控制器跨工程和扩展音频写入守卫保持不变。

时间线观察探针 `artifacts/timeline-observer-probe-dc6f5147dc07.json` 和 `artifacts/timeline-observer-probe-2455465b7ff1.json` 观察到该样本的更新通知在提交时而非暂存期间到达；终点缺失时生成新 tempo 对象。整片删除观察见 `artifacts/timeline-observer-probe-6f666cc0d21f.json`。这些样本不证明任意事件碰撞或地址复用。旧版扩展时间用例在守卫处失败，见 `artifacts/feature-acceptance-3a0d2e3fcd45/summary.json`。

`ProjectArchiveNoteArrays.cs`、`ProjectArchiveNoteIntegration.cs` 和归档事务在受测 AI 音符上保留 `directPitches` 项未知字段：按所属原生音符绑定，upsert 使用选中 tick 保留字段，replace 创建无旧字段的点，clear 删除对应字段；暂存、历史恢复与保存核对完整原生点集。相同 tick 的身份策略是桥接契约，不是原生点对象身份声明。未证明的复制、拆合、剪贴板、源轨合并及素材捕获受保护；清除最后字段后仍跟踪该会话以支持 undo，保存并重新打开无该字段的工程后重新确定范围。混合 controller 和音高项扩展同时保存并保留双方守卫。

`ScoreOperations.cs` 将已有 `pitch.set` 请求锚点校验前移到原生暂存阶段，提交后仍再次读回。私有原生探针 `artifacts/pitch-set-native-5c4bdb0f4c9b.json` 在人工注入暂存错误时观察到回滚；自然 readback 不匹配尚未复现，不把注入错误称为自然故障。

`ProjectInterchange.cs` 在源工程没有轨道、未选择 tempo 且全局字段和资源均相同时，直接返回空操作结果，保持目标原有脏状态和历史。旧版错误置脏记录在 `artifacts/feature-acceptance-101ad64d1010/summary.json`；新用例覆盖本来干净和本来已修改的目标。

最终定向整合 `artifacts/feature-acceptance-1de6c1d0abc4/summary.json` 为 10 个功能用例及清理共 11 通过：含受限时间线、tempo/拍号/controller/音频守卫、音高项扩展往返与重复 tick 保护、素材和合并回归、音高边界与空操作状态。混合扩展单项及清理通过见 `artifacts/feature-acceptance-97ee96429bd9/summary.json`；普通音符拆合诊断及扩展项打开/保存通过见 `artifacts/feature-acceptance-1dec42d402a5/summary.json`。旧版音高项打开失败基线为 `artifacts/feature-acceptance-63223b91968a/summary.json`。上述不是完整历史套件重跑。

构建 0 警告、0 错误；构建前 Roslyn 语义预检覆盖 25 个 C# 文件和 211 个引用，Python AST、PowerShell 探针语法及操作目录检查通过。`artifacts/mcp-smoke-051e87aed535.json` 的新独立 stdio 连接报告 0.13.0、37 个工具，创建、编辑、保存、重开和音符往返通过，前台句柄不变。整合回执记录无自有前台切换或遗留会话。本对话现有连接本轮仍报告 Python MCP 0.4.0；本机 app-server 的 `config/mcpServer/reload` 没有线程或服务选择参数，可能涉及其他已加载会话，且没有可见入口指向本对话所属 app-server，因此未执行全局刷新或重启客户端。

## 保留边界与审查

扩展时间中的 tempo/拍号/controller/音频/音高项组合、音高项扩展复制拆合及跨工程迁移、其他非实体数组、更多音频资源组合、物理 MIDI 和真实 DAW/插件隔离仍待处理。此前自动审查拦截了 controller 跨工程及扩展音频写入的集中放行；另拦截带归档元数据素材属性更新守卫解除，原因是缺少扩展素材端到端验证且可能丢失元数据。上述拒绝均未绕过；素材属性更新仍等待用户明确确认及单项审批。
