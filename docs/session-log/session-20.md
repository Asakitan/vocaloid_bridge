# 会话 20：主音量扩展、时间事件移动与音高身份

日期：2026-11-10。起点提交：`9f08cea24181d990274bcc24b686f4b884df677f`。源码版本 0.15.0；完整目标继续进行。

## 范围与实现

仅使用 VOCALOID:AI 声库、工作区合成样本和私有后台原生会话，不安装经典试用，不操作用户编辑器或已有 DAW/MIDI 端点。三个 `gpt-6.1-terra` 子 agent 分别研究素材属性事务、音高项身份操作和 tempo/拍号插入移动；主线核对实现、修正夹具、补齐主音量项并统一验收。

`ProjectArchiveMasterAutomation.cs` 与归档历史为受测 `masterTrack.volume.events` 未知字段提供按选中 tick 的事务策略：同 tick 更新保留未知字段，replace 保留未删除的既有点和零点字段，删除后重建不继承字段。暂存、历史恢复及保存核对完整原生点集；带主音量项扩展的时间编辑和轨道音量/声像项扩展仍受保护。旧宿主在打开扩展样本时拒绝，见 `artifacts/feature-acceptance-cf2525ff1615/summary.json`；新用例还覆盖删除/重建、undo/redo、clone/reopen、重复 tick、轨道项守卫和源保护。

`ProjectArchiveTimeline.cs` 为受测时间插入扩展了 tempo/拍号事件的一对一移动。安装版托管 `InsertSilence` 对插入起点之后的 tempo 调用 `MoveTempo`，对当前拍号之后的事件调用 `MoveTimeSig`；候选及实际操作分别核对完整事件对象、目标位置和值，并将未知字段纳入原生历史。两个 `include_tempo` 值、多个拍号事件、undo/redo、clone/reopen 和源保护在合成样本通过；原生 Move 内部实现仍未观察，删除或生成带扩展事件不包含在此结论。旧宿主守卫红基线为 `artifacts/feature-acceptance-af0d8654963c/summary.json`。

`ProjectArchiveNoteIntegration.cs` 允许受测 `directPitches` 项扩展轨道复制、轨道属性/重排、片段属性和片段跨轨移动。提交前从原生对象重新核对所有旧音高 owner 和完整点集；同形片段目标在移动或复制前拒绝。普通原生跨轨重叠本身在 `artifacts/feature-acceptance-830932006da1/summary.json` 中被接受，故扩展工程的同形目标检查是桥接歧义保护，不是原生重叠限制。音高项删除、拆合、跨工程及素材捕获仍受保护。

## 素材属性与审查

普通自有 AI 素材回归 `artifacts/feature-acceptance-5f2872117662/summary.json` 复现 `media_update` 删除 `property.json` 顶层及 `part` 内的未知字段。同进程两个不同根的原生管理器未按预期隔离，探针失败记录为 `artifacts/feature-acceptance-7069a2a902c4/summary.json`。独立私有进程暂存、锁定替换失败及成功刷新对照见 `artifacts/feature-acceptance-e07cbc63bd95/summary.json`；主线发现探针文件的夹具 ID 又出现先用后赋值，修正后复验及清理通过，见 `artifacts/feature-acceptance-6db3c881f0f0/summary.json`。该探针只恢复一个顶层标记，提交后刷新失败、并发和通用嵌套合并尚未验证。普通素材生产路径未改变，具体边界见 `docs/media-property-preservation-20.md`。

此前自动审查拦截的控制器跨工程、扩展工程音频写入和带归档元数据素材属性更新守卫均保持，未绕过。素材更新仍需足够事务证据、明确单项确认及相应审批。

## 验证

唯一一次 Release 构建为 0 警告、0 错误；构建前 Roslyn 语义检查覆盖 28 个 C# 文件和 208 个引用，Python AST 覆盖 69 个文件，新 PowerShell 探针语法及操作目录检查通过。

定向整合 `artifacts/feature-acceptance-5b8f6372f11d/summary.json` 为 18 通过、2 失败，含清理，且无自有前台切换或遗留会话。两项失败分别是旧自动化测试创建经典轨后缺声库，以及跨轨测试假设空轨必有 `parts`；只修改测试为 AI 轨和原生空列表写法后，`artifacts/feature-acceptance-17fec2e1ace1/summary.json` 的两项及清理均通过。原失败回执保留，不将两次计数相加为全量结果。未重跑完整历史套件。

主音量/tempo 混合扩展和音高/controller 混合守卫的两个用例及清理另在 `artifacts/feature-acceptance-551c645ece17/summary.json` 通过。

`artifacts/mcp-smoke-ab3f21416991.json` 的新独立 stdio 连接报告 0.15.0、37 个工具，创建、编辑、保存、重开和音符往返通过，前台句柄不变。本对话现有连接本轮仍报告 Python MCP 0.4.0、0 会话；其原生宿主此前比对为 0.5.0。[OpenAI MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) 列出桌面设置的重启流程，但没有证明其针对本对话单独生效；未操作前台或执行全局刷新。

后续仍需素材属性字段的完整事务设计、变化事件的时间删除/生成映射、音高项删除和拆合、其他非实体数组、物理 MIDI 与真实 DAW 隔离，以及受审查约束的独立守卫工作。
