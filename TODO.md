# 当前目标

交付供 Agents 使用的 VOCALOID6 后台功能；仅 AI 声库，保留创建、打开、编辑、保存。

## 开发项：已收齐

- [x] 0.26.0：VOCALOID 后台实例由 MCP 按需启动、启停/重启及确认退出后的新建/重开；活动工程保护和不重放失联请求。

- [x] 复杂扩展时间编辑：跨片段边界、MIDI/AI/音频、音高/控制器/自动化元数据和起始 tempo。
- [x] 素材元数据：控制器、直接音高、其他数组及音频片段字段的捕获/导入与原生历史。
- [x] 其他对象数组：自然键/已知投影、提交前核对、删除/替换和冲突回滚。
- [x] 事务边界：读回异常在提交前回滚；元数据地图合并与原生 no-op 历史。

## 最后交付项：已确认

- [x] 客户端绑定确认 0.26.0：新建的 Claude Code 聊天经自身 MCP 连接列出 38 个工具，单次 `vocaloid_status` 返回 `mcp_version=0.26.0`、原生引擎 6.13.3.1、0 会话，实际 desktop 与预期私有 desktop 一致。随后用 `vocaloid_runtime stop` 结束这次拉起的空闲实例，缓存、运行副本和私有临时目录已清理。只查了这一次状态，没有重跑功能测试；原 Codex 聊天返回 `Transport closed` 的旧传输没有再重试，也不称为已恢复。回执：`artifacts/mcp-binding-confirmed-36.json`。

当前没有未完成项。功能矩阵仍有 8 个 I 行，范围说明见 [STATUS](STATUS.md)；它们未列为开发项。

## 固定约定

复杂实现由主 agent 完成；简单任务可分派给 Haiku 子 agent（此前 Codex 会话为 GPT-6-luna 仅只读资料整理）。全后台，仅必要测试，临时文件在 E 盘，交付前清理自有临时文件。硬件 MIDI、真实 DAW、经典试用与主观听音不属于验收范围。身份歧义、原生能力/范围错误继续明确返回错误，不静默丢字段。

## 历史

- [会话索引](docs/session-log/README.md)
- [会话 33](docs/session-log/session-33.md)：冲突决策与扩展基本事务。
- [会话 34](docs/session-log/session-34.md)：剩余实现、三项必要验收及最终连接切换。
- [会话 35](docs/session-log/session-35.md)：MCP 托管后台实例的按需启动、启停与恢复。
- [会话 36](docs/session-log/session-36.md)：Claude Code 新聊天的绑定确认与交付收尾。
