# 会话 36：客户端绑定确认与交付收尾

日期：2026-11-10。版本：0.26.0，无代码改动。起点提交：`9626ced39c17b1c77ae015ae835c0176a9572250`。

## 用户要求

查看项目并完成当前剩余 TODO；简单任务可分派给 Haiku 子 agent。

## 范围

TODO 只剩一项：客户端重新建立 MCP 工具绑定后确认 0.26.0，只查一次状态，不重跑功能测试。本会话是新建的 Claude Code 聊天（桌面应用 Code 页，Claude Code 2.1.317），拥有自己的 `vocaloid6-native` 服务进程，其启动命令与用户级 `.claude.json` 的条目一致。它不是原 Codex 聊天的旧传输。

## 观察

- 客户端工具列表含 38 个 `vocaloid6-native` 工具，包括 0.26.0 新增的 `vocaloid_runtime`。
- 单次 `vocaloid_status`：`mcp_version=0.26.0`、`backend=native-vsm`、原生引擎 6.13.3.1、0 会话、代次 1、`fallbacks=false`，实际 desktop 与 `isolation_desktop_expected` 相同。
- 该调用按设计拉起私有原生实例，随后用 `vocaloid_runtime stop` 结束，`discarded_sessions=0`。停止后原生进程已退出，缓存命名空间在 VSM 与 VSMCaches 下均不存在，`.runtime/tmp` 和 `.runtime/mcp-temp` 为空，运行副本目录没有新增，`output` 没有新文件。
- 静态核对：`server.py` 38 个工具，`operations.json` 127 个操作，`generate_operation_catalog.py --check` 通过；原生构建时间晚于全部 C# 源文件。

回执：`artifacts/mcp-binding-confirmed-36.json`。

## 未执行

没有重跑功能测试、修改代码或重建原生宿主。原 Codex 聊天的旧绑定没有重试，不称为已恢复。同一桌面应用中另一个 Claude Code 进程持有独立的服务进程，未触碰。剩余工作只有一次状态调用和文档回填，没有分派子 agent；Haiku 分派约定已记入 TODO。

## 仍保留的边界

功能矩阵的 8 个 I 行状态不变。经典 DSE 声库（C-09、C-11、C-16）、物理 MIDI（U-02）和实际听音（U-01）按固定约定不属于验收范围；M-08 余下不接管的用户全局播放开始模式；P-13 的非 44100 Hz 内部合成和 L-08 的其余特殊素材组合未列为开发项。`.github/copilot-instructions.md` 中“完整编辑器功能覆盖已验证”一项因此保持未勾选，`vocaloid_status` 的 `known_limitations` 同样保留。

运行中观察到：实例正常停止后，`.runtime` 仍留下一个 0 字节的 `VocaloidBridge-<id>.stderr.log`，生产清理不删除它。本次只手动删除自己的那一个，没有改代码。

## 清理

删除本次状态检查的 1 个 0 字节 stderr 日志，记录于 `artifacts/cleanup-36.json`。更早遗留的 430 个 stderr 日志（18 个非空）和 8 个运行副本目录归属未确认，保持原样。
