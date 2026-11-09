# 会话 19：音高复制、速度碰撞与素材属性证据

日期：2026-11-10。起点提交：`364979eec40451e5576b2dd02fe125e8aff479d7`。源码版本 0.14.0；完整目标继续进行。

## 范围与实现

仅使用 VOCALOID:AI 声库、私有后台原生会话和工作区合成样本；不安装经典试用、不操作用户编辑器或已有 DAW/MIDI 端点。三个 `gpt-6.1-terra` 子 agent 分别研究扩展事件时间线、直接音高项复制及私有素材属性行为；主线审查代码、修正集成问题并统一验收。

`ProjectArchiveNoteIntegration.cs` 与 `ProjectArchivePreservation.cs` 对 `note.duplicate` 和 `part.duplicate` 校验源与副本完整原生音高点集，并根据返回的音符对象及唯一语义签名深拷贝未知字段。两音符、四个不同嵌套标记的合成用例覆盖源不变、撤销重做和保存重开。重复音符签名样本在打开时受保护，不能据此声称复制路径冲突测试通过；`track.duplicate`、拆合、跨工程、剪贴板和素材捕获仍受保护。旧宿主复制红基线为 `artifacts/feature-acceptance-89eb15811c5b/summary.json`；原生点观察见 `artifacts/pitch-copy-extended-native-9abedbb8a0f3.json`。

`ProjectArchiveTimeline.cs` 在原有 MIDI/AI 实体候选预检基础上，仅当带扩展的 tempo 或拍号地图在原生暂存及提交后逐项保持身份、位置和值时允许时间编辑；没有扩展的事件种类仍按原生行为变化。`preservation.timeline_event_unchanged` 覆盖带不同标记的正负例、历史、重开和源保护，以及只有 tempo 带扩展时未扩展拍号的变化。控制器、直接音高项和 Audio 轨组合仍受保护；发生移动、删除、生成或碰撞的带扩展事件尚无通用映射。旧宿主正例在整体守卫处失败的基线为 `artifacts/feature-acceptance-6f72924aa999/summary.json`。

`ProjectArchiveTempoMerge.cs` 按已观察的原生 `PasteTempo` 语义处理合并碰撞：源事件占用目标 tick 时，源值及源未知字段整体替换目标事件及其字段；无碰撞目标字段保留。原生普通碰撞探针及相同值探针分别为 `artifacts/feature-acceptance-37a783143bc6/summary.json` 和 `artifacts/feature-acceptance-be3cee07697d/summary.json`；旧宿主扩展碰撞因守卫失败为 `artifacts/feature-acceptance-1b6ab06201bd/summary.json`。新用例覆盖带扩展和普通源、不同及相同值、源目标字段、历史、源保护及重开；补充 tick 零碰撞和撤销见 `artifacts/feature-acceptance-d49e68e1f57f/summary.json`。

## 素材属性观察与审查

独立原生媒体管理器仅操作复制到唯一 `artifacts` 子目录的合成 AI 素材。成功修改名称、速度和标签后，整份 `.vsclip` 及其归档字段保持字节不变；锁定 `property.json` 的失败写入保持文件及缓存读数不变。给该副本的 `property.json` 注入嵌套未知字段后，原生成功保存删除了该字段；回执为 `artifacts/feature-acceptance-39dc398383e1/summary.json`。该结果是具体的属性字段丢失风险，不证明桥接写后导入、所有资源组合或崩溃原子性。详见 `docs/media-update-probe-19.md`。

此前自动审查拦截的控制器跨工程与扩展工程音频写入守卫、带归档元数据素材属性更新守卫均保持，未绕过。素材更新还需明确用户确认、针对性验证及单项审批；普通属性写入也应考虑未知 property 字段保留。

## 验证

构建前 Roslyn 语义预检最初发现两个受保护指针访问，按程序集公开显式转换修正；复检覆盖 27 个 C# 文件、208 个引用，0 错误。Python AST 覆盖 64 个文件，两个新 PowerShell 探针语法及操作目录检查通过。唯一一次 Release 构建为 0 警告、0 错误。

定向整合 `artifacts/feature-acceptance-970ae8c4e0d2/summary.json` 为 14 个功能用例及清理共 15 通过，包含上述改动与控制器、音频、素材及混合扩展守卫；未记录自有前台切换或遗留会话。之后仅补跑新增 tick 零碰撞及清理，均通过。没有重跑完整历史套件。

`artifacts/mcp-smoke-fa30988634d9.json` 的新独立 stdio 连接报告 0.14.0、37 个工具，创建、编辑、保存、重开及音符往返通过，前台句柄不变。本对话现有连接本轮仍报告 Python MCP 0.4.0、0 会话；其原生宿主此前比对为 0.5.0。全局 reload 可能影响其他会话，没有执行或重启用户客户端。

后续仍需变化的 tempo/拍号事件映射、音高项拆合/跨工程、其他非实体数组、更多音频资源组合、物理 MIDI 和真实 DAW 隔离验收，以及受审查约束的独立守卫工作。
