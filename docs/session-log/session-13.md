# 会话 13：剪贴板资源、速度合并、拍号与 ANSI 探针

日期：2026-11-10。起点提交：`8f8507e`。本轮源码版本 0.8.0；总目标继续进行。

## 目标与分工

继续只使用 VOCALOID:AI 声库和后台私有原生会话，不安装经典声库试用，不接管用户编辑器或连接现有 DAW/MIDI 端点。子 agent 分别实现速度事件扩展合并、拍号事件扩展编辑，以及自有合成 ANSI IPC 边界探针；主线实现剪贴板工程资源迁移并审阅整合。

## 修改与证据

`ProjectClipboard.cs` 和 `ProjectArchiveTransfer.cs` 在 AI/MIDI 轨道、片段、音符选择中携带独立源快照的完整不透明工程级 ZIP 成员。剪切保留源工程级资源；粘贴复用同路径同字节资源，检查内容、大小写和文件/目录冲突，新增成员与实体变更一同进入撤销历史。新增资源时，独立候选先打包并验证 ZIP，再修改真实目标；仅有资源而无实体扩展时也走该路径。旧版拒绝剪切的记录为 `artifacts/feature-acceptance-1a8e9b24ebfe/summary.json`。

`ProjectArchiveTempoMerge.cs` 按明确的源、目标 tick 映射受测 tempo 未知字段：替换采用来源，偏移合并保留目标并加入来源，重叠 tick 报错。候选和真实事务均核对原生完整结果，数据进入历史。`ProjectArchiveArrays.cs`、`ProjectArchivePreservation.cs` 与 `ScoreOperations.cs` 对拍号的 `bar/numer/denom` 建立受测编辑映射，覆盖修改、移位、删除后重建、撤销重做、克隆及重开；来源或目标带拍号扩展的速度/拍号地图合并仍在目标变更前受保护。

首次集成构建只报告 `ProjectClipboard.cs` 缺少 `System.IO`，补齐后构建 0 警告、0 错误。`artifacts/feature-acceptance-5f7c71ba55ed/summary.json` 为 12 项功能及清理通过、1 项失败；失败是旧测试仍要求已支持的 tempo 合并被拒绝。更新预期为真实合并、字段及撤销验证后，`artifacts/feature-acceptance-0f5180183d62/summary.json` 的定向用例及清理通过，原失败回执保留。合成资源测试覆盖轨道、片段、音符复制、音符剪切、来源关闭、资源复用、字节/大小写/前缀冲突、撤销重做及重开。两次验收均未记录自有宿主的前台切换，也没有遗留自有会话；不是完整套件重跑。

在资源用例补充剪切后的粘贴和与原生音频文件名碰撞的候选预检后，`artifacts/feature-acceptance-9cc33036cca5/summary.json` 的用例与清理通过，目标状态和已引用 WAV 均保持，未记录自有宿主的前台切换或遗留会话。

独立 stdio 状态回执 `artifacts/stdio-v080-status-6b5f065e679c.json` 报告 0.8.0、37 个工具及原生后台。`artifacts/mcp-smoke-129fd1680c28.json` 验证新连接的创建、修改、保存、重开、关闭和音符往返，测试前后前台窗口一致。本对话现有连接此前报告 Python 0.4.0，原生子进程此前对应 0.5.0；需重新连接才能加载当前版本，未重启用户客户端或编辑器。

`tools/probe_iat_ansi_fixture.c` 与 `tools/probe_iat_ansi_host.c` 只对自有随机管道和自有合成 DLL 做全信任静态 IAT 命中计数。`artifacts/probe-iat-ansi-boundary.txt` 记录静态 ANSI 调用命中，而加载初始化、动态解析和另一个模块的调用绕过该补丁；它不证明名称改写、AppContainer ANSI 隔离或实际 Yamaha 插件行为。首次沙箱编译被拒绝，提权后完成合成测试；工作区根目录生成的临时链接文件已清理。

## 剩余边界

拍号扩展合并、其他非实体数组、原生音频资源所有权、纯元数据合并历史、其他编辑的同形歧义、物理 MIDI 与实际 DAW/插件隔离仍待处理。资源副本保留到会话关闭，重复撤销分支可能累积磁盘占用。无声库试用安装、用户前台操作或替代引擎。
