# 模块映射

| 源文件 | 功能 | Status |
| --- | --- | --- |
| `native/Program.cs` | 原生宿主入口、安装库解析、私有 desktop 检查 | 已编译 |
| `native/EngineSession.cs` | VSM 会话、工程生命周期、声库、片段渲染和归档校验钩子 | 独立命名空间、零结果缓存；保存前 ZIP 及控制器事务校验有定向测试 |
| `native/ProjectIntegrity.cs` | 原生打开与发布前的结构和声库身份检查 | 缺经典声库预检、丢失身份阻止覆盖、AI 正例通过；不代替经典声库 |
| `native/ScoreOperations.cs` | 结构化轨道、片段、音符、曲线与历史编辑 | 68 操作；21 AI 首音符、扩展删除/拆合和普通编辑有定向证据 |
| `native/AudioOperations.cs` | 原生离线音频、效果与整轨混缩 | 16 操作；扩展工程音频导入/编辑及效果添加/撤销通过，复杂资源组合另列边界 |
| `native/TransportOperations.cs` | 原生设备枚举与私有会话播放、停止、定位、释放 | 普通及扩展工程快照的 DirectSound 静音闭环通过；定位区分异步请求与观测 |
| `native/TrackFreezeOperations.cs` | 会话自有冻结缓存、时基物化和作者态保存 | 多片段/非零起点/效果/自动化与正式 MCP 通过；不持久化冻结标志 |
| `native/ProjectArchivePreservation.cs`、`native/ProjectArchiveArrays.cs` | 实体身份、事件与未知字段 | 原生身份映射、音频 region 区分、元数据地图 no-op/历史通过 |
| `native/ProjectArchiveTimeEdit.cs`、`native/ProjectArchiveNoteArrays.cs`、`native/ProjectArchiveNoteIntegration.cs`、`native/ProjectArchiveMasterAutomation.cs`、`native/ProjectArchiveTrackAutomation.cs` | 复杂时间编辑与曲线元数据 | MIDI/AI/音频跨边界、曲线迁移、起始 tempo 及历史的必要用例通过 |
| `native/MidiRecordingOperations.cs`、`native/MidiRecordingGuards.cs` | 设备枚举、MIDI 事件队列、事务录制及会话保护 | 六操作、静音同步、回调保护及自有虚拟输入通过；物理设备和驱动错误路径未验 |
| `native/LibraryOperations.cs` | 原生音素、样式与媒体库 | 32 操作；完整短语检查、三语言及 21 AI 首音符往返定向通过 |
| `native/MediaPropertyOperations.cs`、`native/MediaPropertyJournal.cs` | 独立原生属性写入、独占发布及持久恢复 | 显式版本化冲突决策、决策中断恢复、普通与归档 clip 字节保持有定向证据 |
| `native/ProjectInterchange.cs`、`native/ProjectArchiveTempoMerge.cs`、`native/ProjectArchiveTimeSigMerge.cs` | 原生格式交换、复制、恢复与合并 | 真实 PPSF3/音频克隆、受测纯元数据历史及空操作状态、tempo/拍号扩展合并和速度碰撞覆盖通过；其他音频组合受限 |
| `native/ProjectClipboard.cs`、`native/ProjectArchiveTransfer.cs` | 私有原生剪贴板及扩展身份迁移 | 音高、控制器、轨道自动化复制/剪切/迁移及偏移有 0.24.0 定向证据 |
| `native/ProjectArchiveOutput.cs` | 带扩展工程的独立原生快照输出 | 人声渲染、MIDI 导出、离线混缩/分轨及源会话历史保护定向通过 |
| `native/ProjectArchiveLibrary.cs`、`native/ProjectArchiveMedia.cs` | 素材元数据 v1/v2、音频绑定与候选核对 | 控制器/音高/其他数组/音频捕获导入、单次历史及重开通过 |
| `native/RpcServer.cs` | 单线程 JSON 行协议、原生对象发现与精确签名调用 | 已编译 |
| `vocaloid_bridge/native_client.py` | 私有进程、握手、代次、缓存及故障生命周期 | 按需启动、默认保护、确认退出重建和不重放失联请求通过定向验证 |
| `vocaloid_bridge/server.py` | 38 个 MCP 工具、资源、写歌提示 | 增加托管 runtime 启停入口，所有工作保留在私有后台实例 |
| `vocaloid_bridge/compose.py` | AI 编曲/替换缺省音素共用原生 G2PA、临时会话和独占发布 | asa 日英中单音节、替换源身份及保存重开定向通过；其他声库、扩展源及发音质量待验 |
| `vocaloid_bridge/operations.json` | 原生 dispatch 对照的随包操作索引 | 127 操作均有精确契约行；发现与实测分开 |
| `tools/generate_operation_catalog.py` | 操作目录生成及漂移检查 | 按源码与文档操作首列精确生成，缺契约行时检查失败 |
| `vocaloid_bridge/projects.py` | VPR 结构化编排 | AI 音符按显式源快照保留；JSON Patch 的受测 sidecar 跟随移动/复制和删除；扩展边界及源句柄保护 |
| `vocaloid_bridge/music.py` | MIDI、音符与路径校验 | 定向检查通过 |
| `vocaloid_bridge/templates/ai-starter.vpr` | 原生编辑器生成的 AI 片段模板 | 本机样本 |
| `vocaloid_bridge/desktop.py` | 旧 UI 模块退役标记 | 不包含可调用后端 |
| `tools/smoke_mcp.py` | 真实 stdio 原生生命周期及 MCP 版本验收 | 0.17.0 独立连接通过 |
| `tools/render_demo.py` | MCP stdio 编曲、保存、重开、合成和 WAV 样本验收 | 通过：374849 帧，非零峰值与 RMS，关闭后 0 会话 |
| `tools/verify_features.py`、`tools/verify_all.py` | 按功能分类的真实 MCP 验收 | 历史整合 76/5/2；本轮定向证据及环境边界见 STATUS |
| `tools/check_host_isolation.py` | 双原生宿主缓存回归 | 修复前失败、每宿主命名空间后通过 |
| `tools/check_*remaining*.py` | 乐谱、音频、素材、交换的定向验证 | 证据与限制分别记录在模块文档 |
| `tools/check_session_features.py` | VPR 导入、完整表现、素材参数与 Breath 音频 | 参数往返及 Breath 启用/频率/音量差异通过，类型声音差异未成立 |
| `tools/check_robot_runtime.py`、`tools/check_audio_routing.py` | Robot 时序/缓存和内部/输出率调查 | 原失败回归、双会话及六组合混音通过，非 44100 内部合成显式报错 |
| `tools/check_voicecolor_audio.py`、`tools/check_score_parameters.py` | VoiceColor 和 Take 定向音频测量 | 三个 AI VoiceColor 及 Take 差异通过；六个经典 VoiceColor 待 DSE |
| `tools/check_transport.py`、`tools/check_track_freeze.py` | 设备传输和冻结的真实 MCP/原生回归 | 正式入口、失败清理、作者态及静音传输通过 |
| `tools/check_project_preservation.py` | 扩展数据和原生对象历史回归 | 未知字段、嵌套、额外资源、替换及参数编辑通过 |
| `tools/check_midi_recording.py`、`tools/check_midi_recording_case.py` | MIDI 显式事件流、静音同步及操作目录回归 | 已验无硬件事件流及静音输出；虚拟输入另有用例 |
| `tools/check_midi_owned_input.py` | 已安装 SDK 创建临时 MIDI 输入并通过 WinMM 回调录制 | 虚拟输入、保存重开及新进程端口消失通过；物理设备未验 |
| `tools/check_midi_callback.ps1`、`tools/check_clipboard_extension_guard.py`、`tools/check_clipboard_resources.py` | 输入回调错误和剪贴板工程资源回归 | 回调逻辑与 AI 资源迁移定向通过；硬件输入仍待验证，旧入口调用当前资源用例 |
| `tools/check_archive_transfer.py`、`tools/check_clipboard_extended_cut.py`、`tools/check_archive_merge.py`、`tools/check_tempo_merge.py`、`tools/check_timesig_merge.py` | 扩展剪切、跨工程粘贴及合并回归 | 受测实体、偏移、历史、工程级不透明资源及 tempo/拍号扩展合并通过 |
| `tools/check_archive_audio_transfer.py`、`tools/check_archive_output.py` | 扩展音频轨资源迁移及原生快照输出回归 | 受测同名来源、原始/处理 WAV、历史及非零音频、MIDI 导出通过 |
| `tools/check_controller_splitting.py`、`tools/check_controller_transfer.py` | 控制器边界拆合和跨工程传输回归 | 工程内边界与冲突回滚通过；跨工程用例因现有保护未通过 |
| `tools/check_archive_library.py`、`tools/check_archive_audio_mutations.py` | 扩展工程私有素材/离线音频及普通音频事务回归 | 受测路径通过；扩展工程音频导入/编辑用例仍受保护 |
| `tools/check_archive_media_extensions.py`、`tools/check_archive_transport.py`、`tools/check_audio_effect_history.py` | 扩展 AI 素材、静音快照传输及普通效果事务回归 | 受测正例、历史与保护定向通过；设备和格式组合有边界 |
| `tools/check_pitch_clear_boundaries.py`、`tools/check_metadata_history.py` | 音高清除边界及纯元数据原生历史回归 | 定向 MCP 用例及旧历史、冲突、最高速度通过 |
| `tools/check_note_array_extensions.py`、`tools/run_pitch_clear_native_probe.py`、`tools/run_timeline_identity_probe.py` 及其 PowerShell 探针 | 音符数组与时间线原生身份和边界观察 | 受测音高项扩展往返和私有 desktop 取证通过；生成点及其他未知字段仍有限制 |
| `tools/run_pitch_item_observer_probe.py`、`tools/run_timeline_observer_probe.py`、`tools/check_pitch_set_transactions.py` 及其 PowerShell 探针 | 私有原生事件通知和暂存读回/回滚观察 | 观察提交时通知及注入失败回滚；不等于所有事件身份可映射 |
| `tools/check_archive_media_update.py` | 自有普通素材更新及扩展素材红色基线 | 普通更新/锁文件失败通过；扩展素材更新守卫解除被自动审查拦截 |
| `tools/check_tempo_metadata_noop.py`、`tools/check_media_native_19.py` 及相关 PowerShell 探针 | 速度碰撞覆盖、相同地图扩展历史和隔离素材属性写入 | 受测速度覆盖及历史通过；原生素材属性保存会删除合成未知字段 |
| `tools/check_master_automation_20.py`、`tools/check_part_overlap_native_20.py`、`tools/check_media_*_20.py` 及相关 PowerShell 探针 | 主音量项事务、片段重叠及素材属性暂存验证 | 主音量项及普通重叠原生观察通过；普通素材未知字段丢失，独立进程暂存仍缺失败事务证据 |
| `tools/check_track_automation_21.py`、`tools/check_timeline_delete_21.py`、`tools/check_note_delete_guards_21.py`、`tools/check_media_process_21.py` | 轨道自动化项、时间删除、音高删除守卫与素材暂存定向验证 | 轨道项及部分时间删除通过；音高删除守卫保持，素材仅合成夹具手工恢复字段 |
| `tools/check_timeline_meter_22.py`、`tools/check_extension_edit_guards_22.py`、`tools/check_track_edits_22.py`、`tools/check_controller_notes_22.py` | 拍号生成边界、现有守卫与潜在普通编辑正例 | 受测空位拍号生成及守卫通过；普通编辑候选为红基线，审查守卫未变 |
| `tools/check_timeline_meter_collision_23.py`、`tools/probe_media_atomic_23.py` | 占用拍号碰撞预期正例和自有文件共享探针 | 拍号正例为守卫红基线，解除被审查拦截；文件共享观察不构成完整事务 |
| `tools/check_file_event_identity_24.py`、`tools/check_score_noop_24.py`、`tools/probe_media_transaction_24.py` | 文件事件字段归属、轨道 no-op 和合成文件锁定探针 | 文件事件/轨道 no-op 定向通过；文件锁观察不构成生产事务 |
| `tools/check_source_snapshot_25.py`、`tools/check_score_noop_25.py`、`tools/check_file_note_identity_25.py`、`tools/probe_media_atomic_25.py` | 源工程竞争、轨道字段 no-op、音符原型和素材文件锁探针 | 源一致性及轨道字段定向通过；音符错贴为红基线，素材原生刷新恢复未验 |
| `tools/check_file_notes_26.py`、`tools/probe_note_identity_26.py`、`tools/probe_ai_note_defaults_26.py`、`tools/probe_ai_lyrics_conversion_26.py`、`tools/probe_media_handle_26.py` | 文件音符身份、AI 默认/歌词转换和素材同句柄探针 | 显式身份及原生往返通过；空音素、转换错误及素材事务仍待处理 |
| `tools/check_patch_sidecar_27.py`、`tools/check_patch_semantics_27.py`、`tools/probe_patch_sidecar_27.py`、`tools/probe_patch_copy_validity_27.py`、`tools/probe_lyrics_native_27.py`、`tools/probe_native_note_27.py` | JSON Patch sidecar 身份与 AI 转换观察 | 受测 sidecar 迁移和原生重开通过；自动转换及其他组合待验证 |
| `tools/check_lyrics_staging_28.py` 及 `tools/probe_*28.py` | 歌词暂存边界与原生音素引导调查 | 一项暂存隔离用例通过；自动转换、原生失败恢复和其他声库仍待验证 |
| `tools/check_compose_phonemes_29.py` | AI 编曲自动音素、发布及保存重开 | 一项三语言功能用例及清理通过；失败注入和其他声库未验 |
| `tools/check_replace_phonemes_30.py` | 替换自动音素与源音符身份 | 一项三语言及源字段用例通过，文件返回契约、保存重开、sidecar 拒绝和清理通过 |
| `tools/check_note_add_31.py`、`tools/check_lyrics_transactions_31.py`、`tools/check_lyrics_rollback_31.ps1`、`tools/check_media_properties_31.py` | 首音符、歌词提交前回滚及普通素材属性 | 三个直接相关用例及各自清理通过，未扩为全量验收 |
| `tools/check_native_semantics.ps1`、`tools/clean_owned_caches.py` | 完整原生语义预检与历史自有缓存清理 | 预检使用真实 WPF global usings；清理按回执和进程创建时间保留活动/未知项 |
| `tools/check_clipboard_ambiguity.py`、`tools/check_archive_export_limits.ps1`、`tools/check_tempo_array_helper.ps1` | 剪贴板候选、ZIP 导出限制和 tempo 数组原语回归 | 合成候选、缩小阈值 ZIP 和原语通过；完整 MCP 证据见 STATUS |
| `tools/probe_appcontainer_pipe.cs`、`tools/probe_appcontainer_child.go` | 随机合成管道的后台进程隔离探针 | 受限令牌及单一默认权限管道拒绝访问已观察；非插件隔离证明 |
| `tools/probe_appcontainer_server.cs`、`tools/probe_appcontainer_server_child.go`、`tools/probe_appcontainer_peer.cs`、`tools/probe_appcontainer_peer_child.go` | 随机合成管道受限服务端与同/异 profile 对端探针 | LOCAL 双向收发和负对照已观察；未证明真实插件隔离 |
| `tools/probe_appcontainer_mapping*.cs`、`tools/probe_appcontainer_mapping_child.go`、`tools/probe_appcontainer_iat_child.go`、`tools/probe_mapping_*.c` | 随机合成名称映射和自有 DLL 静态导入重定向 | 自有 DLL 的两项宽字符静态导入对照通过；非真实插件或完整 IPC 证明 |
| `tools/probe_iat_ansi_fixture.c`、`tools/probe_iat_ansi_host.c` | 自有 ANSI 导入槽及动态解析时序探针 | 观察到加载初始化、动态解析和第二模块绕过；未验证实际插件隔离 |
| `tools/check_audio_recording.py` | 录音与宿主接口静态证据 | 仅读取安装文件；未加载 VST 或打开音频输入 |
| `tools/check_internal_rate_static.py` | 安装版本的采样率分支取证 | 只读静态证据；不当作 96 kHz 动态验收 |
| `tools/fetch_public_ppsf_fixture.py` | 公开样本获取及来源记录 | 作者原始 PPSF3 与最小格式夹具分开标识；歌曲不入 Git |
| `docs/feature-matrix.md` | 官方手册与原生接口逐项覆盖 | 证据已回填，未验、缺失和受限项保留 |
| `.vscode/mcp.json` | 工作区 stdio 服务配置 | 已配置 |
| `.vscode/tasks.json` | 安装、工程验收和原生合成验收任务 | 原生合成任务已运行通过 |
| VS Code Stable/Insiders 用户 `mcp.json` | 跨工作区启动原生 MCP | 已注册；配置及共用启动检查通过 |
| Claude Code 用户 `.claude.json` | 用户级 stdio MCP | 原生命令报告 Connected |
| Claude Desktop `Claude-Data` / `Claude-3p` 配置 | 桌面客户端两种模式的 stdio MCP | 已注册；配置及共用启动检查通过，界面连接未验 |
| Codex 用户 `config.toml` | 用户级 stdio MCP，180 秒工具期限 | enabled；配置及共用启动检查通过 |
| `tools/check_media_recovery_32.py`、`tools/media_journal_child_32.ps1` | 素材发布阶段、进程终止与外部冲突 | 四阶段断言及独立冲突用例通过；测试脚本参数/编码失败记录保留 |

| `native/ProjectArchiveDeletion.cs`、`native/ProjectArchivePitchMigration.cs` | 目标绑定删除与音高拆合来源校验 | 定向删除/撤销、拆合及来源冲突回滚通过 |
| `tools/check_agent_completion_33.py`、`tools/media_resolution_child_33.ps1` | 0.24.0 Agent 调用、崩溃与扩展事务验证 | 五项契约分别通过；失败回执保留，不计作全量通过 |

| `native/ProjectArchiveNestedArrays.cs` | 其他对象数组的自然键、已知投影与暂存核对 | voices/语言/效果参数/颤音等元数据编辑和往返定向通过；身份歧义报错 |
| `tools/check_completion_34.py`、`tools/check_transaction_readback_34.ps1` | 剩余时间、素材、数组、提交前失败与纯元数据历史 | 三项必要契约最终通过；原失败回执保留 |

| `tools/check_runtime_35.py` | MCP 托管生命周期与未知结果不重放 | 两个定向用例及清理通过；无原生重编译 |

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
| 2026-11-10 | 升级 0.2.1：109 操作，Robot 零缓存修复、PPSF3 真实样本、项目完整性保护、全部表现参数及 Take/AI VoiceColor 定向验证；经典与外部环境边界保留。 |
| 2026-11-10 | 升级 0.3.0：119 操作，原生设备传输、会话冻结、未知字段/资源与历史保留；定向回归通过，扩展格式及经典资源边界继续保留。 |
| 2026-11-10 | 升级 0.4.0：125 操作，默认 AI 轨、扩展数据复制、MIDI 事件流和静音同步定向通过；硬件输入、拆合与 DAW 边界保留。 |
| 2026-11-10 | 升级 0.5.0：未知字段拆合、AI 剪切/粘贴/合并与旧历史、MIDI 错误逻辑通过；额外资源、固定 DAW 管道隔离与硬件输入仍待验证。 |
| 2026-11-10 | 升级 0.6.0：root/master 受测扩展合并及历史、独立虚拟 MIDI 输入和随机 LOCAL 管道对照通过；物理设备、额外资源和实际插件隔离仍待验证。 |
| 2026-11-10 | 升级 0.7.0：受测 tempo 扩展、不透明资源合并、剪贴板歧义预检和 ZIP 限制通过；其他数组、剪贴板资源与真实插件隔离继续保留边界。 |
| 2026-11-10 | 升级 0.8.0：受测剪贴板资源迁移、tempo 扩展合并、拍号事件扩展编辑及 ANSI 合成边界探针；拍号扩展合并和真实插件隔离继续保留边界。 |
| 2026-11-10 | 升级 0.9.0：受测拍号扩展合并、控制器事件编辑、音频资源迁移及扩展工程原生输出；控制器扩展迁移和实际插件隔离继续保留边界。 |
| 2026-11-10 | 升级 0.10.0：受测控制器扩展工程内复制拆合、独立素材/音频操作及普通音频撤销历史；控制器跨工程与扩展音频写入仍受保护。 |
| 2026-11-10 | 升级 0.11.0：受测 AI 素材未知字段及历史、扩展工程静音快照传输和普通效果历史；扩展时间编辑与 controller/音频写入边界保留。 |
| 2026-11-10 | 升级 0.12.0：音高半开清除和受测纯元数据/资源合并历史通过；时间事件生成点及素材更新审查边界保留。 |
| 2026-11-10 | 升级 0.13.0：受限 AI 扩展时间线、音高项未知字段及历史通过；空合并保持状态，自动审查边界保留。 |
| 2026-11-10 | 升级 0.14.0：音高项音符/片段复制、速度碰撞和不变扩展事件地图通过；素材未知属性丢失风险及审查边界保留。 |
| 2026-11-10 | 升级 0.15.0：主音量项、插入事件移动及音高项身份操作定向通过；普通素材未知属性丢失与事务边界继续调查。 |
| 2026-11-10 | 升级 0.16.0：轨道音量/声像项和部分时间删除的受测元数据事务通过；音高删除守卫及素材未知字段风险保持。 |
| 2026-11-10 | 升级 0.17.0：受测空位拍号边界生成及原生身份通过；普通编辑守卫放宽被自动审查拦截，素材刷新竞争有新证据。 |
| 2026-11-10 | 升级 0.17.1：125 个操作均有精确参数契约；拍号碰撞守卫放宽被自动审查拦截，主音量与文件共享仅有有限原生/系统观察。 |
| 2026-11-10 | 升级 0.17.2：文件 tempo/控制曲线未知字段按受测 tick 保留，同名轨道更新保持脏状态；受审查守卫保持不变。 |
| 2026-11-10 | 升级 0.17.3：源工程同句柄读取/复制及轨道字段组合 no-op 定向通过；音符原型错贴与素材事务保留为未完成。 |
| 2026-11-10 | 升级 0.18.0：AI 文件音符显式源身份、干净新音符和 sidecar 索引保护定向通过；空音素及素材事务继续调查。 |
| 2026-11-10 | 升级 0.19.0：JSON Patch 的受测无效音素 sidecar 随移动、复制和删除迁移；原生歌词转换边界补充实证。 |
| 2026-11-10 | 升级 0.19.1：歌词与音素应用/重置先检查暂存变更，避免提交无关编辑；自动音素转换继续调查。 |
| 2026-11-10 | 升级 0.20.0：`score_compose` 的 AI 单音节缺省音素通过原生 G2PA 与临时会话转换，受测 asa 三语言往返通过。 |
| 2026-11-10 | 升级 0.21.0：AI 编曲和替换音符共用原生音素转换；替换源选择器、标准字段、保存重开及 sidecar 拒绝定向通过。 |
| 2026-11-10 | 升级 0.22.0：受测 AI 首音符、歌词撤销事务、普通素材未知字段与锁定失败通过；临时根迁至 E 盘并清理已证实结束的 C 盘缓存。 |
| 2026-11-10 | 升级 0.23.0：素材访问串行化、独占发布、持久日志和提交前/后进程中断恢复，外部文件抢占保留原数据。 |
| 2026-11-10 | 0.24.0：显式素材冲突决策、21 AI 首音符、完整短语、扩展删除/拆合/迁移、占用拍号与扩展音频定向验证。 |
| 2026-11-10 | 0.25.0：复杂时间事务、素材元数据 v2、其他数组与读回回滚/元数据 no-op，剩余实现收齐。 |
| 2026-11-10 | 0.26.0：MCP 按需拉起和管理 VOCALOID 私有实例，活动工程保护、确认退出后重建及失联不重放。 |
