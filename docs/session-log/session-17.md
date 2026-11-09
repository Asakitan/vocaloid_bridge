# 会话 17：音高边界、纯元数据历史与身份探针

日期：2026-11-10。起点提交：`15115c7d7549916dddc6667f36ffa4e7247fce10`。本轮源码版本 0.12.0；总目标继续进行。

## 目标与分工

继续使用后台私有原生会话及 VOCALOID:AI 声库，不安装经典试用，不操作用户编辑器或已有 DAW/MIDI 端点。子 agent 分别调查扩展时间编辑、带归档元数据的素材属性更新及客户端连接和音符数组；主线审查取证并修复普通音高清除边界、补齐受测纯元数据合并的原生历史。

## 修改与证据

`WIVSMNote.ClearDirectPitches` 在受测样本中包含两个端点，而 MCP 的 `pitch.clear` 约定是半开区间。旧版在清除 `[100, 400)` 时误删 400 点，随后回读失败；旧回执为 `artifacts/feature-acceptance-6ecaa6f48952/summary.json`。私有桌面原生原语探针 `artifacts/pitch-clear-native-08cb8e42a1df.json` 分别观察精确端点、单 tick、相邻区间和全清除。`ScoreOperations.cs` 对局部清除传入 `end_tick - 1`，全清除仍用原生 sentinel；在原生提交前核对完整剩余点，失败时交给已有事务回滚，再于提交后复核。

`ProjectInterchange.cs` 对没有其他原生暂存变更、也没有 tempo/拍号扩展事务的纯 root/master 字段或不透明资源合并，在同一原生事务内暂时改变并恢复初始 tempo，以建立真实撤销项；最终速度不变。标题修改的原生负探针 `artifacts/feature-acceptance-3c8c061ca1fb/summary.json` 没有产生暂存历史；速度暂存与恢复的探针 `artifacts/feature-acceptance-068f1d7bd636/summary.json` 验证了独立撤销项及更早历史。原守卫基线 `artifacts/feature-acceptance-55ade680ca91/summary.json` 因没有原生历史项而拦截纯元数据/资源合并。

整合回执 `artifacts/feature-acceptance-b07ec74aa41d/summary.json` 为 5 个功能用例及清理共 6 通过，覆盖音高边界、纯元数据合并、原有工程和资源合并及曲线回归。扩展目标、旧历史、冲突、相同内容的无操作合并及最大原生速度边界补充验证通过，见 `artifacts/feature-acceptance-fc6a72130b1c/summary.json`；音高无效区间、单 tick 与保存重开见 `artifacts/feature-acceptance-ecd0ad6f2b5c/summary.json`。这些定向结果均无自有前台切换或遗留会话，不是完整历史套件重跑。

`tools/run_timeline_identity_probe.py` 及私有桌面原生探针观察插入/删除前后的 tempo、拍号、片段、音符和 controller 指针。移除区间终点 tempo 后，原生删除生成新的边界事件，回滚后重复操作生成的对象地址不同，见 `artifacts/timeline-identity-probe-81519e73308a.json`；候选对象地址不足以映射真实事务生成事件，扩展时间编辑守卫保留。普通非对齐编辑的序列化和历史探针见 `artifacts/feature-acceptance-e64467f2aa7f/summary.json`。

音符 `directPitches` 探针观察到拆分/合并生成 `ZeroPitch` 和负位置点，未知数组字段仍由现有守卫保护；修正证据复制后的探针及清理通过，见 `artifacts/feature-acceptance-c76ddf7a946f/summary.json` 与 `docs/note-array-preservation.md`。该结果不证明任意点的身份迁移。

普通自有 MIDI 素材属性更新及锁定 `property.json` 的失败探针通过，见 `artifacts/feature-acceptance-2456c42fd76b/summary.json`；前者只改变属性文件，受测 `.vsclip` 不变。带归档元数据的素材更新期望成功用例在旧守卫处失败，见 `artifacts/feature-acceptance-720b23a039dd/summary.json`，其后续断言未执行。自动审查拦截了移除该守卫的请求，原因是缺少扩展素材重建和端到端验证，存在元数据丢失风险；守卫保持不变并已向用户请求明确确认。此前 controller 跨工程和扩展音频写入守卫解除也曾被自动审查拦截，均未绕过。

构建 0 警告、0 错误；构建前 Roslyn 语义预检覆盖 22 个 C# 文件和 211 个引用，Python AST 及操作目录检查通过。新独立 stdio 状态 `artifacts/stdio-v0120-status-d5e0884e5809.json` 报告 0.12.0、37 工具和 0 会话，生命周期烟雾 `artifacts/mcp-smoke-4d27c828d657.json` 验证创建、编辑、保存、重开及前台句柄不变。本对话现有 MCP 连接本轮仍报告 Python 0.4.0；另一个子 agent 的独立连接曾报告 0.11.0，不代表本对话连接已更新。没有强制重启客户端或用户编辑器。

## 剩余边界

扩展时间编辑、控制器跨工程与素材传输、扩展音频写入、带归档元数据的素材属性更新、音符和其他非实体数组、无原生暂存变更时的 tempo/拍号扩展合并、物理 MIDI 及真实 DAW/插件隔离仍待处理。实测范围只覆盖相应合成 AI 工程、设备与输入组合。
