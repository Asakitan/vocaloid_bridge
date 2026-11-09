# 当前状态

日期：2026-11-10。版本：0.17.2。完整目标继续进行，不把受测范围扩大为所有输入与环境组合。

用户明确选择仅使用 VOCALOID:AI 声库，不安装经典试用。未指定类型的 `track.create` 默认创建 `MidiAi`；显式经典轨及旧工程的源文件与身份保护保留。较早的功能和验证历史见 [会话索引](docs/session-log/README.md)。

## 当前入口与实现

- 37 个 MCP 工具，68 个乐谱、16 个音频、30 个素材、5 个剪贴板和 6 个 MIDI 录制操作，共 125 个；创建、打开、编辑、保存、关闭、克隆和恢复保留。会话 23 补齐其中 18 个原先为空的契约行，并补充音符、控制器、声库、音频和素材操作的公共选择器；生成器按操作首列精确匹配并拒绝缺项；可发现不等于所有输入与环境均已验收。
- 工程未知字段、固定嵌套对象、额外 ZIP 资源及受测 AI 实体扩展按原生身份与历史保存；受测 tempo/拍号扩展插入和部分删除、音高项扩展编辑与复制、主音量及轨道音量/声像项扩展编辑有定向证据。
- 会话 24 修正文件级 `score_tempo` 和 `score_curve` 的事件未知字段错贴：原有 tick 保留自身字段，删除点丢弃字段，新点不继承字段；重复源位置在输出创建前拒绝。单独传入相同名称的 `track.update` 保持 clean/dirty 状态，且仍检查原生暂存变更。
- 会话 21 新增轨道音量/声像项的 owner 与完整点集事务：同 tick 更新保留未知字段，删除后重建不继承字段；受测轨道属性/重排、undo/redo、保存、克隆及重开通过。跨工程及未验证的轨道变更仍受保护。
- 会话 21 新增受测时间删除事件映射：已删除事件不保留字段，保留事件沿原生身份迁移，新生成 tempo 边界不继承字段。会话 22 增加不同拍号且开始小节未占用的生成边界：新拍号不继承未知字段；开始位置碰撞及初始 tempo 删除仍受保护。其他受保护的扩展时间组合保持不变。
- 独立原生设备传输、轨道冻结、扩展工程快照输出、MIDI 事件流与自有虚拟输入均有定向证据；这些结果不等于物理 MIDI、真实 DAW 或任意声库/效果组合的验收。

## 本轮证据

本轮构建前 Roslyn 语义检查覆盖 26 个 C# 源文件、生成的全局 using 文件及 208 个引用，Python AST 覆盖 82 个文件；一次 Release 构建为 0 警告、0 错误。只运行改动相关检查，未重跑完整历史套件。

| 范围 | 回执 | 结果 |
| --- | --- | --- |
| 文件事件、轨道 no-op、生命周期及守卫 | `artifacts/feature-acceptance-f4c4b6029e12/summary.json` | 9 个功能用例及清理共 10 通过；独立 stdio 返回 0.17.2，无自有前台切换或遗留会话 |
| 文件事件工具说明及映射复验 | `artifacts/feature-acceptance-6615c4d86e30/summary.json` | 两个功能用例及清理共 3 通过，含工具描述与字段归属 |
| 旧版文件事件及轨道 no-op 红基线 | `artifacts/feature-acceptance-da5678235623/summary.json`、`artifacts/feature-acceptance-410a03ae2d30/summary.json` | 新事件误继承首事件字段、既有控制点错贴，以及同名更新错误置脏均已复现；失败记录保留 |
| 主音量时间与文件锁定探针 | `artifacts/master24-missing.json`、`artifacts/master24-adjacent.json`、`artifacts/media-transaction-24-e9c72d5172d0/receipt.json` | 多边界生成/迁移与显式回滚为有限观察；范围锁外竞争写入成功而替换失败，生产事务未建立 |
| 0.17.1 目录、私有剪贴板与生命周期 | `artifacts/feature-acceptance-95209afa6b83/summary.json` | 3 个功能用例及清理共 4 通过；独立 stdio 返回 0.17.1，零自有前台切换和遗留会话 |
| 选择器和默认参数补齐后的目录复验 | `artifacts/feature-acceptance-dba5e14102fe/summary.json` | 目录用例及清理通过；125 个操作均有首列契约，八项单独查询核对关键字段，不等于全部功能组合验收 |
| 拍号占用碰撞 | `artifacts/timeline-identity-probe-eee54488979d.json`、`artifacts/feature-acceptance-7e646bbd736f/summary.json` | 合成普通工程中既有对象保留身份并更新拍号；带未知字段正例被守卫拦截，后续断言未执行 |
| 主音量时间点及文件共享 | `artifacts/master23-probe-c9e1fe80edaa.json`、`artifacts/media-atomic-23-dbc4a1ee15e6/receipt.json` | 主音量生成点及回滚身份为有限观察；受测共享模式锁定时写入/替换失败，解锁后替换成功，事务仍未建立 |
| 拍号生成边界及现有守卫 | `artifacts/feature-acceptance-80b1c4779514/summary.json` | 12 个功能用例及清理共 13 通过；无自有前台切换或遗留会话 |
| 0.17.0 独立 stdio 生命周期 | `artifacts/mcp-smoke-cf2c42db8233.json` | 37 工具；创建、编辑、保存、重开及音符往返通过，前台句柄不变 |
| 原生拍号身份与旧版红基线 | `artifacts/timeline-identity-probe-47ef55371dd5.json`、`artifacts/feature-acceptance-336f60d13d89/summary.json` | 合成样本中生成对象为新身份，旧版守卫拒绝正例；清理通过 |
| 普通编辑守卫红基线 | `artifacts/feature-acceptance-dd354933659d/summary.json`、`artifacts/feature-acceptance-72bcbfa55a05/summary.json` | 轨道自动化八项及控制器音符正例被现有守卫拦截，后续断言未执行；单独保留测试 |
| 素材替换与锁定刷新探针 | `artifacts/media-failure-22-045a23ff9013/receipt.json` | 检查/替换间外部写入被覆盖；锁定时刷新返回成功值但枚举漏项及旧引用失效，解锁重刷仅新枚举恢复 |
| 轨道自动化、时间删除、音高守卫及生命周期 | `artifacts/feature-acceptance-e8eb9b6496cb/summary.json` | 16 个功能用例及清理共 17 通过；无自有前台切换或遗留会话 |
| 0.16.0 独立 stdio 生命周期 | `artifacts/mcp-smoke-acbdb340d53d.json` | 37 工具；创建、编辑、保存、重开及音符往返通过，前台句柄不变 |
| 旧宿主轨道项及时间删除红基线 | `artifacts/feature-acceptance-79945951763e/summary.json`、`artifacts/feature-acceptance-cfe62cee3296/summary.json` | 旧守卫拒绝预期正例，清理通过；不是新版失败 |
| 音高项删除红基线 | `artifacts/feature-acceptance-830a85e95c28/summary.json` | 四种删除路径被现有守卫拦截，后续元数据断言未执行；实验正例未计入发布验收 |
| 普通素材属性及独立进程暂存 | `artifacts/feature-acceptance-25f45d337d42/summary.json`、`artifacts/feature-acceptance-2ca7dc2676b2/summary.json` | 原生更新实际丢失顶层和 `part` 未知字段；独立进程探针仅手工恢复已知夹具标记并检测一次提交前变化 |
| 上轮主音量、事件移动及音高身份 | `artifacts/feature-acceptance-5b8f6372f11d/summary.json`、`artifacts/feature-acceptance-17fec2e1ace1/summary.json` | 首轮 18 通过、2 失败；两项测试夹具修正后复验通过，原失败记录保留 |
| 历史完整验收 | `artifacts/feature-acceptance-012574702338/summary.json` | 76 通过、5 失败、2 缺样本；不可与定向批次相加为全量通过 |

更多逐批回执及历史失败见 [会话索引](docs/session-log/README.md)。真实 PPSF3 样本、原生合成和 AI 声库证据见 [会话 07](docs/session-log/session-07.md)。

## 保留边界

1. **未知字段与审查**：`directPitches` 项的删除、拆合和跨工程仍受保护。自动审查拦截了单独解除四个删除守卫的请求：目标绑定删除钩子尚未集成，可能丢失元数据；守卫保持原位，未集成候选也未进入编译。会话 22 的轨道自动化/控制器扩展普通编辑组合守卫放宽也被拦截，原因是候选仍为红基线、原生身份与失败回滚证据不足，可能静默丢失元数据；相关守卫未改变。会话 23 的占用拍号边界守卫放宽同样被自动审查拦截：未知字段往返与原生失败回滚尚未建立，存在元数据丢失风险，且需针对该守卫单项批准。控制器扩展跨工程、扩展工程音频写入及带归档元数据素材属性更新的既有审查守卫保持原位，相关事务需要足够原生证据和单项审批。
2. **文件级音符替换**：静态检查发现 `score_replace_notes` 以首个音符作为新音符原型，可能复制其未知字段；尚未做对应动态验证或更改，涉及 `directPitches` 时仍遵守已有审查边界。文件级 tempo/曲线修复不代表该路径已无损。
3. **普通素材属性**：生产 `media_update` 会丢失受测 `property.json` 未知字段。独立进程探针已证实检查后到替换前的并发写入可被覆盖；锁定素材时刷新返回成功值但枚举漏项且旧引用失效，解锁重刷只观察到新枚举恢复。通用数组身份、竞争隔离、失败后完整恢复和崩溃持久性尚未建立。详见 [素材属性调查](docs/media-property-21.md) 和 [刷新探针](docs/media-failure-22.md)。
4. **时间与迁移**：拍号生成时开始位置碰撞、初始 tempo 删除、controller/音频/音高项/主音量项/轨道自动化项扩展的时间编辑，以及轨道自动化项跨工程传输等仍受保护。tempo/拍号扩展在无原生暂存变更时仍有合并限制；不宣称任意 VPR 无损编辑。详见 [工程保留](docs/project-preservation.md)。
5. **设备与宿主**：物理 MIDI 采集和设备错误、真实 DAW 固定管道隔离与同步、实际听音质量仍未完成验收。内部声乐合成明确要求 44100 Hz，混缩输出采样率独立。
6. **客户端**：新独立 stdio 连接实测 0.17.2；本对话连接本轮仍报告 Python MCP 0.4.0、0 会话，原生宿主此前比对为 0.5.0。可见的 app-server 全局刷新没有线程或服务选择参数，可能影响其他会话，本轮未执行；没有操作用户前台编辑器。

当前模块状态见 [功能矩阵](docs/feature-matrix.md)、[会话 24](docs/session-log/session-24.md) 和 [TODO](TODO.md)。
