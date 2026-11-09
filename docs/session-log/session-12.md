# 会话 12：剪贴板、资源、速度事件与合成 DLL

日期：2026-11-10。起点提交：`0360113`。本轮源码版本 0.7.0；总目标继续进行。

## 目标与分工

保持 AI 声库、后台私有桌面和原工程保护。子 agent 分别处理工程不透明资源、速度事件数组和 DAW 合成隔离；主线实现剪贴板候选预检、归档输出限制、交叉审阅和统一验收。

## 修改与证据

`ProjectClipboard.cs` 对带扩展粘贴先在独立目标中执行并验证保存重开，失败时不把剪贴板标记为已使用。旧版 `artifacts/feature-acceptance-2a5e6d2cb2f5/summary.json` 记录同形轨道粘贴成功但目标保存报歧义；本轮定向回归验证该情况在真实目标变更前报错，偏移后的粘贴、等数据副本、撤销重做和重开成功。

`ProjectArchiveTransfer.cs` 和归档历史在轨道合并时迁移受测的不透明工程级资源：相同路径相同字节复用，内容、大小写或文件与目录前缀冲突报错，候选保存发现与原生 WAV 的碰撞。资源映射参与撤销、重做、分支和保存重开；私有副本保留到会话关闭。旧版 `artifacts/feature-acceptance-5db61aec641e/summary.json` 记录资源迁移被原保护拒绝；此前 `artifacts/feature-acceptance-81c433b89a49/summary.json` 是测试夹具缺少 `bpm` 的失败，已修正夹具，原回执未改写。

`EngineSession.cs` 在发布 VPR 前检查实际 ZIP 条目数、未压缩大小、路径大小写与文件/目录冲突；带新增资源的候选也先打包并检查，避免两个各自合规的输入合并后生成超过现有提取限制的输出。`tools/check_archive_export_limits.ps1` 用缩小的数量和字节阈值验证这些分支，回执 `artifacts/archive-export-4717c45e9a45.json` 通过；该回执不等于实际 8 GiB 大文件测试。最初两次脚本调用分别因 PowerShell 反射参数包装及异常包装处理而失败，修正测试脚本后通过，原终端输出保留。

`ProjectArchiveArrays.cs` 和 `ScoreOperations.cs` 对受测 `masterTrack.tempo.events` 未知字段建立显式操作映射：位置/值修改沿用字段，删除后同值重建不继承，历史、克隆及保存重开同步。带 tempo 扩展的速度地图合并仍在目标变更前受保护；效果参数和语言数组仍受保护。旧二进制在打开 tempo 扩展时的失败见 `artifacts/feature-acceptance-39d061aa7454/summary.json`。

最终原生构建 0 警告、0 错误。`artifacts/feature-acceptance-a2ec5efb0ad1/summary.json` 为本批 9 个定向功能用例及清理共 10 项通过，覆盖上述剪贴板、资源、tempo、旧合并及保留 guard；受控宿主无前台切换，结束时自有会话为零。这不是完整历史套件重跑。

DAW 隔离调查使用本机已安装 MSVC 和 Windows SDK 编译自有合成 DLL。`artifacts/probe-appcontainer-iat-controls-acl.txt` 记录将其两个宽字符静态导入映射到随机 `LOCAL` 管道后，同 profile 收发成功，不同 profile 和全信任负对照未找到管道；首次 DLL 加载权限失败的回执另保留。两份新建合成 DLL 的临时读取执行 ACE 已移除并复核继承权限。此测试不是 Yamaha 插件、ANSI 或动态解析、其他 IPC、真实 VST3/ARA 宿主及同步的证明。

## 剩余边界

其他非实体数组、剪贴板及原生音频资源迁移、tempo 扩展合并、纯元数据历史、其他结构化编辑的同形歧义、物理 MIDI 和真实 DAW 仍待处理。当前对话连接仍报告 Python MCP 0.4.0，运行中的原生宿主此前对应 0.5.0；`artifacts/stdio-v070-status-0dd9be424fba.json` 记录独立 stdio 进程报告 0.7.0、37 个工具和 0 会话，现有客户端需重新连接后核对版本。未启动经典试用或接管用户编辑器。
