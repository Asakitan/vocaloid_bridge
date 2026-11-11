# 当前目标

交付供 Agents 使用的 VOCALOID6/7 后台功能；仅 AI 声库，保留创建、打开、编辑、保存。当前版本 0.30.0：41 工具/130 操作，V7 身份误报及 Robot 后台修复、参数检查与原生 AI 生成/音高保留已完成定向验收，见 [会话 46](docs/session-log/session-46.md)。

## 已完成历史

- [x] 0.28.0：临时文件自动清理。MCP 启动时及之后每 10 分钟删除超过一小时的 `output/` 生成文件、`.runtime/mcp-temp` 旧临时文件和已退出宿主的临时目录；手动入口默认 dry-run，`--keep` 可保留匹配项。真实工作区首次清理删除 4573 个文件 / 5.5 GB，失败 0。
- [x] 会话 38：样式捕获关联来源声部，细项参数默认启用对应效果且显式旁路优先；样式应用一次提交，普通/扩展工程保存重开和撤销/重做通过。
- [x] 会话 37：多片段混缩超时修复。目标波形有效且整条原生渲染队列完成后才释放控制器；实际 12 段工程单段、整体混缩及逐段非零样本通过，超时值未改。
- [x] 0.27.0：Agent 作曲流程。`vocaloid_workflow` 给出步骤、歌词写法和 AI 实际演唱的控制项；AI 音符改词时重新生成音素；歌词被拒绝时提示写法；适用范围、取值范围和已安装声库写进返回值。依据是 asa 的逐样本审计和 Haiku 子 agent 的试做。
- [x] 0.26.0：VOCALOID 后台实例由 MCP 按需启动、启停/重启及确认退出后的新建/重开；活动工程保护和不重放失联请求。

- [x] 复杂扩展时间编辑：跨片段边界、MIDI/AI/音频、音高/控制器/自动化元数据和起始 tempo。
- [x] 素材元数据：控制器、直接音高、其他数组及音频片段字段的捕获/导入与原生历史。
- [x] 其他对象数组：自然键/已知投影、提交前核对、删除/替换和冲突回滚。
- [x] 事务边界：读回异常在提交前回滚；元数据地图合并与原生 no-op 历史。

## 交付项

- [x] 公开仓库与 MIT 许可证：`Asakitan/vocaloid_bridge` 为 PUBLIC，默认分支 `master`；`LICENSE` 由 GitHub 识别为 MIT；远端 315 个文件，未包含 `curves/` 或运行产物。

- [x] 客户端绑定确认 0.26.0：新建的 Claude Code 聊天经自身 MCP 连接列出 38 个工具，单次 `vocaloid_status` 返回 `mcp_version=0.26.0`、原生引擎 6.13.3.1、0 会话，实际 desktop 与预期私有 desktop 一致。随后用 `vocaloid_runtime stop` 结束这次拉起的空闲实例，缓存、运行副本和私有临时目录已清理。只查了这一次状态，没有重跑功能测试；原 Codex 聊天返回 `Transport closed` 的旧传输没有再重试，也不称为已恢复。回执：`artifacts/mcp-binding-confirmed-36.json`。

- [ ] 客户端重新连接后确认 0.30.0：先保存关闭工程，再重新连接 `vocaloid6-native`，确认 VOCALOID7、41 工具及 `project_inspect`/`project_ai_adjust`。独立真实 stdio 已通过，当前聊天未暴露 VOCALOID MCP 工具；未替用户重启其他活动实例。
- [ ] V7 混缩、完整参数声音差异与复杂扩展迁移仍未逐项验收；本次到此停止，不自动运行全量。VMM 素材、片段音频效果、反转/变声为明确不支持，见 [V7 兼容说明](docs/vocaloid7.md)。

会话 37 的混缩补丁和会话 38 的样式/参数补丁都需要新宿主：先保存并关闭工程，再重启 MCP 或调用 `vocaloid_runtime restart`。当前聊天没有可直接使用的 VOCALOID MCP 工具，未替用户重启其他活动实例。

V6 历史功能矩阵仍有 7 个 I 行，范围说明见 [STATUS](STATUS.md)；不能直接当作 V7 的验证范围。

## 固定约定

主 agent 负责集成和验收；简单修改直接处理，复杂独立模块可按当前工作区指令分派。全后台，仅必要测试，生成文件在工作区 output 并由既有清理机制管理。硬件 MIDI、真实 DAW、经典试用与主观听音不属于验收范围。身份歧义、原生能力/范围错误继续明确返回错误，不静默丢字段。

## 历史

- [会话索引](docs/session-log/README.md)
- [会话 46](docs/session-log/session-46.md)：V7 身份保护、Robot 后台兼容、功能导航、原生 AI 生成/音高保留；定向 stdio 验收通过。
- [会话 33](docs/session-log/session-33.md)：冲突决策与扩展基本事务。
- [会话 34](docs/session-log/session-34.md)：剩余实现、三项必要验收及最终连接切换。
- [会话 35](docs/session-log/session-35.md)：MCP 托管后台实例的按需启动、启停与恢复。
- [会话 36](docs/session-log/session-36.md)：Claude Code 新聊天的绑定确认，以及 0.27.0 的 Agent 作曲流程。
- [会话 37](docs/session-log/session-37.md)：多片段混缩超时修复与实际工程回归。
- [会话 38](docs/session-log/session-38.md)：样式与细项参数修复，普通/扩展工程的定向验收。
- [会话 39](docs/session-log/session-39.md)：整曲制作中的 `points_file`、逐音符批量补丁与 `batch.run`，AI 声库实测。
- [会话 40](docs/session-log/session-40.md)：公开仓库、MIT 许可证与远端回读。
- [会话 41](docs/session-log/session-41.md)：README 猫娘化、本机记录移出与 CHANGELOG 分离。
