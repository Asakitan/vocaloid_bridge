# 模块映射

| 源文件 | 功能 | Status |
| --- | --- | --- |
| `native/Program.cs` | 原生宿主入口、安装库解析、私有 desktop 检查 | 已编译 |
| `native/EngineSession.cs` | VSM 会话、工程生命周期、声库和片段渲染 | 生命周期、独立缓存与音频克隆通过；Robot 声音差异及经典格式仍失败 |
| `native/ScoreOperations.cs` | 结构化轨道、片段、音符、曲线与历史编辑 | 64 个操作有成功调用；批量、颤音、时序、回滚与换算通过，路由/采样率组合发声待修 |
| `native/AudioOperations.cs` | 原生离线音频、效果与整轨混缩 | 9 个操作、5 种离线处理、11 个内置效果及受测采样格式通过 |
| `native/LibraryOperations.cs` | 原生音素、样式与媒体库 | 30 个操作有成功调用；样式及 HMM 通过，经典 Singing Skill 重开受身份问题影响 |
| `native/ProjectInterchange.cs` | 原生格式交换、复制、恢复与合并 | VSQX 音符样本通过；PPSF V2 音符保留但轨道/声库往返失败 |
| `native/ProjectClipboard.cs` | 私有原生快照剪贴板 | 5 个操作及源关闭后的 MIDI 跨工程粘贴通过 |
| `native/RpcServer.cs` | 单线程 JSON 行协议、原生对象发现与精确签名调用 | 已编译 |
| `vocaloid_bridge/native_client.py` | 私有 desktop、Job Object、管道客户端与 DLL 快照 | 独立构建副本启动、关闭清理通过 |
| `vocaloid_bridge/server.py` | 36 个 MCP 工具、资源、写歌提示 | 36 工具均有真实 stdio 成功调用 |
| `vocaloid_bridge/operations.json` | 原生 dispatch 对照的随包操作索引 | 由生成器维护，区分入口发现与实测 |
| `tools/generate_operation_catalog.py` | 操作目录生成及漂移检查 | 按源码和文档生成 |
| `vocaloid_bridge/projects.py` | VPR 结构化编排 | 音素扩展冲突写入被拒绝，无关修改及重开通过 |
| `vocaloid_bridge/music.py` | MIDI、音符与路径校验 | 定向检查通过 |
| `vocaloid_bridge/templates/ai-starter.vpr` | 原生编辑器生成的 AI 片段模板 | 本机样本 |
| `vocaloid_bridge/desktop.py` | 旧 UI 模块退役标记 | 不包含可调用后端 |
| `tools/smoke_mcp.py` | 真实 stdio 原生生命周期验收 | 通过 |
| `tools/render_demo.py` | MCP stdio 编曲、保存、重开、合成和 WAV 样本验收 | 通过：374849 帧，非零峰值与 RMS，关闭后 0 会话 |
| `tools/verify_features.py`、`tools/verify_all.py` | 按功能分类的真实 MCP 验收 | 本轮整合 76 通过、5 失败、2 缺样本；定向差异见 STATUS |
| `tools/check_host_isolation.py` | 双原生宿主缓存回归 | 修复前失败、每宿主命名空间后通过 |
| `tools/check_*remaining*.py` | 乐谱、音频、素材、交换的定向验证 | 证据与限制分别记录在模块文档 |
| `docs/feature-matrix.md` | 官方手册与原生接口逐项覆盖 | 证据已回填，未验、缺失和受限项保留 |
| `.vscode/mcp.json` | 工作区 stdio 服务配置 | 已配置 |
| `.vscode/tasks.json` | 安装、工程验收和原生合成验收任务 | 原生合成任务已运行通过 |
| VS Code Stable/Insiders 用户 `mcp.json` | 跨工作区启动原生 MCP | 已注册；配置及共用启动检查通过 |
| Claude Code 用户 `.claude.json` | 用户级 stdio MCP | 原生命令报告 Connected |
| Claude Desktop `Claude-Data` / `Claude-3p` 配置 | 桌面客户端两种模式的 stdio MCP | 已注册；配置及共用启动检查通过，界面连接未验 |
| Codex 用户 `config.toml` | 用户级 stdio MCP，180 秒工具期限 | enabled；配置及共用启动检查通过 |

## 更新记录

| 日期 | 更新 |
| --- | --- |
| 2026-11-09 | 建立原生后台 MCP；用私有 desktop 和原生 VSM 替代早期 UI 探针。 |
| 2026-11-09 | 原生 MCP 生命周期通过；加入用户提供仓库的结构和功能边界对照。 |
| 2026-11-09 | 最终四音符原生往返通过；WAV 合成超时作为明确阻塞保留。 |
| 2026-11-10 | 修复干净序列跳过 Commit 导致渲染队列为空；实际 MCP 保存、重开、人声 WAV 合成与关闭通过。 |
| 2026-11-10 | 注册 VS Code、Claude Code/Desktop 与 Codex 用户级 MCP，六处配置与项目外启动验证通过。 |
| 2026-11-10 | 建立完整功能矩阵并补原生编辑、音频、媒体和工程交换入口，保留首轮失败证据。 |
| 2026-11-10 | 最终完整 MCP 验收 45/45；35 个工具、81 个结构化操作受测通过，清单保留未覆盖功能。 |
| 2026-11-10 | 非零起点音频素材捕获加入私有 WAV 区域物化；实际采样和保存重开定向验证通过。 |
| 2026-11-10 | 新增五种语言静态音素参考表；标明手册版本和非原生枚举，实际 MCP 调用通过。 |
| 2026-11-10 | 新增轨道音量、声像和主音量自动化；事件往返和实际混音 PCM 对比通过。 |
| 2026-11-10 | AI 次声库素材往返通过；Attack/Release 初始化前查询为空，初始化后的结果见后续记录。 |
| 2026-11-10 | Yamaha VSQX 4 和公开 VSQX 3 实际样本完成音符、歌词、音素及 VPR 重开验收；PPSF 样本未提供。 |
| 2026-11-10 | 新增片段高级表现读写；Robot 原生脚本在后台恢复，真实合成与混缩通过。 |
| 2026-11-10 | 原生 Attack/Release 目录为 36/42；传统和 AI 素材及无效音素扩展定向通过，文件级冲突拒绝；PPSF V2 真实样本暴露轨道/声库重开丢失。 |
| 2026-11-10 | 含手册和 VSQX3/4、PPSF V2 样本的完整 MCP 验收 60 通过、1 失败；35 工具及 91 个结构化操作有成功调用。 |
| 2026-11-10 | 升级 0.2.0：36 工具、108 操作有成功调用；新增样式、HMM、细化编辑、操作目录和独立缓存。整合仍有经典格式、Robot 及缺样本项。 |
