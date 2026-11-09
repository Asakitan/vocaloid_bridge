# 会话 11：全局扩展、虚拟 MIDI 输入与合成管道

日期：2026-11-10。起点提交：`6da7937`。本轮源码版本 0.6.0；总目标继续进行。

## 目标与分工

保持 AI 声库、后台私有桌面和原工程保护。子 agent 分别处理 root/master 扩展合并、独立 MIDI 输入与 DAW 合成 IPC 对照；主线复核源码、补充嵌套父对象预检、统一构建并执行定向验收。

## 已完成及验证

`ProjectArchivePreservation.cs` 的历史快照同时记录实体、root 和 master 的未知字段，旧历史升级基线保留原有全局字段。`ProjectArchiveTransfer.cs` 先合并相等或不同指针的源字段，对同指针不同值在目标变更前报错；新增嵌套字段先用独立目标快照验证父对象和输出冲突。全局字段新增必须对应原生历史项；源不透明额外资源仍有保护。最终相关构建为 0 警告、0 错误。

`artifacts/feature-acceptance-818d9fb68a28/summary.json` 在新增嵌套预检前验证全局合并、原有剪贴板旧历史、音符拆合与清理，共 4 项通过。其后 `artifacts/feature-acceptance-28ce06be4e32/summary.json` 验证直接和嵌套全局字段的合并、相等和冲突、旧目标历史、保存重开、撤销重做、无原生历史项保护及清理，共 2 项通过。增加仅有根扩展的目标后，`artifacts/feature-acceptance-a32d5b61bf04/summary.json` 暴露同形轨道带不同扩展时合并成功但保存报歧义的失败。现有扩展合并先在独立候选中执行、保存并验证，再修改目标；`artifacts/feature-acceptance-5a2c12f87c28/summary.json` 验证该歧义在目标变更前被拒绝、偏移后的合并及旧历史，共 2 项通过。候选预检增加一次工程复制和原生保存开销；剪贴板等其他编辑路径仍可能到保存时才发现同形歧义。上述都是定向证据，不是全量历史套件。

本机已安装 teVirtualMIDI SDK 和驱动；`tools/check_midi_owned_input.py` 创建随机命名的独立虚拟输入，仅打开名称和 ID 匹配的 WinMM 输入，通过 SDK 发出两条真实短消息。`artifacts/midi-owned-78935c45c6f9.json` 记录两个回调事件、一个音符、编辑、保存重开、会话数归零以及独立新进程中端口消失；未打开现有 CubaseAI 端口或 WinMM 输出。前次 `artifacts/midi-owned-608946611532.json` 因同一长寿命进程仍枚举缓存端口而失败，保留原始回执；新进程枚举的确认方式与原因见 `docs/midi-recording.md`。测试没有安装、卸载或修改现有组件，也没有覆盖物理 MIDI 硬件和实际设备故障。

`artifacts/probe-appcontainer-server.txt` 记录随机合成管道的普通名称和 `LOCAL` 名称服务端创建对照；`artifacts/probe-appcontainer-peer-controls.txt` 记录同 profile 的双向字节交换，以及不同 profile 和全信任客户端未找到目标管道。两个负对照的服务器在超时后由父进程终止并等待；终止 API 返回值和子进程实际 SID 未单独记录。临时 profile 删除 HRESULT 与 desktop 关闭结果已记录。这些结果不证明实际插件、其他 IPC、授权或音频兼容，未加载真实插件。

本对话连接的 Python MCP 进程仍报告 0.4.0；此前其运行中的原生宿主文件与 0.5.0 构建一致。`artifacts/live-mcp-transfer-1794244477025.json` 通过这个实际连接验证扩展 AI 轨道跨工程粘贴、位置偏移、保存和打开，结束时会话数为零。本轮原生改动通过新建的独立 stdio 进程测试；`artifacts/stdio-v060-status-1679c32d6429.json` 确认新进程报告 0.6.0、发现 37 个工具且没有打开会话。未强制重启现有客户端或用户编辑器。

## 后续边界

非实体数组和额外资源跨工程迁移、没有原生历史项的纯元数据合并、物理 MIDI 及驱动错误、实际 DAW 插件隔离和同步、人工听音仍待处理。连接刷新后需核对运行中的 MCP 版本，不把合成管道对照当作实际插件隔离。
