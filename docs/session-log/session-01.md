# Session 01

日期：2026-11-09。

后续：本会话记录的合成超时已于 2026-11-10 修复，实际 MCP WAV 验收结果见 [会话 02](session-02.md)。下文保留当日状态。

## 需求

为本机 VOCALOID6 实现写歌与功能控制 MCP。补充约束：任何功能不得影响前台，不允许回退，MCP 必须自行创建、保存和关闭工程。用户明确要求检查 RPC 或命令行入口。

## 已完成

- 确认本机 Editor 6.13.3 与 .NET 8 程序集。
- 初期 UI 探针取得原生 VPR 模板；在后台 UIA Invoke 检查中观察到前台变化，随后停用并移除 UI 控制实现。
- 反编译启动、文档、序列管理和渲染封装。普通启动会创建窗口；选用原生 VSM 管理器，不调用该入口。
- 最小宿主通过真实新建、保存、关闭、重新打开检查，前台句柄不变。
- 实现私有 Windows desktop、匿名管道、Job Object 和单 STA 线程宿主。
- 实现 24 个 MCP 工具以及 VPR/MIDI 编排；加入原生片段渲染入口。

## 验证

已通过：原生最小生命周期、隔离子进程、MCP 工具注册、VPR/MIDI 定向检查，以及真实 stdio 新建、属性修改、保存、关闭和重开。最终增加四音符工程原生往返验证，证据为 `artifacts/mcp-smoke-1e947e9c5020.json`。

声库枚举得到 21 个可用 Dnn 声库。同步渲染返回 VoiceBankNotFound 后，对照正式启动补齐 DSE 产品模式和异步渲染流程；最后的异步调用在 180 秒内没有返回波形。没有音频替代、UI 回退或合成成功声明。该执行已结束，子进程由其 Job Object 清理。

按用户建议阅读 AI-VOCALOID-MCP，记录在 `docs/references.md`。该项目的 VPR 编排设计可参考，但没有本机合成或编辑器 RPC 后端。

证据分别保存在 `artifacts/reverse`、`artifacts/fixtures`、`artifacts/inspection` 和 `output/native-probe-*.vpr`。原生探针与后续 MCP 会话不接管用户原有编辑器。

## 后续

工程生命周期和音符数据的 stdio 原生验收已完成。后续需在原生合成调度/上下文层定位阻塞；完整 DSP、混缩和所有编辑器功能还未验收。不重新启用 UI，也不反复重跑已通过的生命周期检查。