# 会话 03：客户端安装

日期：2026-11-10。

## 目标与操作

将现有原生 MCP 安装到本机 VS Code、Claude 和 Codex，不重写引擎或影响现有应用。服务名统一为 `vocaloid6-native`。

- VS Code Stable 与 Insiders 的用户 `mcp.json` 增加同名 stdio 条目，原有服务保留；工作区配置不变。
- 使用 `claude mcp add --scope user --transport stdio` 注册 Claude Code。
- 使用 `codex mcp add` 注册 Codex，再将目标条目的 `tool_timeout_sec` 设为 180。
- 商店版 Claude 4.23118.0.0 的安装清单明确将数据迁移到 LocalAppData。向已经存在的 `Claude-Data` 和 `Claude-3p` 目录增加 `claude_desktop_config.json`，不写入旧的 LocalCache/Roaming/Claude 目录，也不更改登录和模型设置。

所有客户端使用绝对 Python 入口，显式设置项目目录、导入路径与 UTF-8。用户近期修改的 `.vscode/tasks.json` 未触碰。

## 验证

- 六处配置均可按 JSON/TOML 解析，命令、参数、环境变量与预期一致。
- 注册后的服务数：VS Code Insiders 12，Stable 10，Claude Code 13，Claude Desktop 两种模式各 1，Codex 14。
- `claude mcp get vocaloid6-native` 报告用户级、Connected；`codex mcp get vocaloid6-native --json` 报告 enabled。
- 使用上述共用配置，以用户主目录为 cwd 完成一次实际 MCP 初始化、24 个工具发现和 `vocaloid_status` 调用；原生 backend 为 native-vsm，实际与预期私有桌面一致，0 工程会话，前台不变。
- 本轮未重复运行已经通过的合成测试，未启动或重启桌面客户端。配置已落盘，桌面界面内的连接显示尚未验收；已有应用或会话需重新加载配置。