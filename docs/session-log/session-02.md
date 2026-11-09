# 会话 02：原生人声合成修复

日期：2026-11-10。

## 目标

修复上一会话的 WAV 合成超时，完成实际 MCP 验收。继续使用私有 Windows desktop、同一 STA 原生宿主；不操作前台，不改用其他音源，不修改安装文件或授权。

## 根因与修复

阶段日志显示原生异步渲染已启用，但 `IsFinishedRendering` 一直为 true，目标片段没有有效乐谱或波形。只读分析安装版 VSM 的导出、RTTI 和调用链发现，`Commit(false)` 在处理编辑之外还会刷新渲染队列。旧代码在 `IsStaged=false` 时跳过 Commit，使已打开的干净工程从未入队。

`native/EngineSession.cs` 现始终在合成前调用 Commit，仅当无暂存编辑且原生错误为 NoError 时接受 false 返回值。保留原生异步渲染、观察者和文件检查；将原生等待限制为 120 秒，外层 RPC 为 180 秒，保证原生错误可返回。临时 Dispatcher 消息泵不是根因，已移除；不保留调试输出。

`vocaloid_bridge/server.py` 的合成工具说明和状态已去掉过期的超时声明。`tools/render_demo.py` 改为实际 MCP stdio 验收；新增任务 `VOCALOID6: native render smoke`。

## 验证

- Release 构建成功。
- 内部原生调用首次成功产物：`output/background-demo-830bef659c.wav`；诊断记录约 344 毫秒取得有效波形。
- 最终实际 MCP 任务通过：编曲、保存、关闭、重开干净工程、合成、保存后音符/歌词/音素读回、关闭。
- 回执：`artifacts/background-demo-31c27fd842.json`。
- 工程：`output/background-demo-31c27fd842.vpr`。
- 音频：`output/background-demo-31c27fd842.wav`，44100 Hz、单声道、16-bit PCM、374849 帧、8.499977 秒，峰值 0.1177368，RMS 0.0138641。
- 原生会话余数为 0，前台句柄前后均为 19992790。

本次合成阻塞已解决。完整编辑器功能覆盖、DSP、混缩和外部插件不是本次修复的验收结论。