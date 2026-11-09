# 会话 26：AI 文件音符身份与音素探针

日期：2026-11-10。起点提交：`0abe22c491377cd9c8fd66d5e10f01a7d13e65fe`。源码版本 0.18.0；完整目标继续进行。

## 文件音符身份

旧代码对每个输出音符复制首音符原型。真实 MCP 红基线 `artifacts/feature-acceptance-79599f48f49f/summary.json` 中，期望选择 B、创建新音符、选择 A，却得到 A/A/A，速度也均为 70。此前 `artifacts/feature-acceptance-4fbd9aaf25c3/summary.json` 因测试假设列表只返回一个内容块而中断，修正为逐音符读取后才得到该红基线。

AI 音符现用 `source={index, expected}` 显式选取源索引及完整 JSON 快照，拒绝重复、越界、过期或类型不一致；无选择器表示新音符，不按 tick 猜测身份。新音符使用已观察 AI 基线，默认 velocity=64，默认语言沿用首源音符或空模板基线；已选音符保留自己的字段，`raw` 按原规则合并。选中音符未改歌词和语言时，省略 phoneme 保留其原音素。经典填充轨沿用先前原型行为，未进行经典试用。

原 `phoneme-validity` sidecar 根据索引和字段校验，无法识别同字段的新音符。新音符替换/编曲先校验源 sidecar，并要求受引用音符在输出原索引保留所选来源，再校验字段；不迁移 sidecar。整个源工程中的 controller-event、track volume/pan-event 及 direct-pitch-item 扩展仍在文件音符替换前受保护；未修改原生守卫或执行受保护扩展操作。

`artifacts/feature-acceptance-57ffec017ade/summary.json` 的一个真实 MCP 功能用例及清理通过，含不同标记/速度、移动、新建、嵌套 raw、无效选择器、原生保存重开、同字段 sidecar 身份冲突和内存内守卫谓词。政策、兼容行为和限制见 [音符身份](../note-identity-26.md)。

## AI 默认音素与转换

三个 `gpt-6.1-terra` 子 agent 分别调查身份契约、AI 原生默认值及素材句柄。`artifacts/feature-acceptance-f4436a433348/ai_defaults26.json` 中，仅空 phoneme、仅缺失 velocity 各自导致受测 AI 项目原生打开时报音符数改变；仅缺失 langID 时 native save 写回 0。显式日语音素的新音符保存重开并渲染，远离旧音符的 WAV 采样区间非零，但未作仅旧音符对照或听音。

`artifacts/feature-acceptance-1ca9890042f3/ai_lyrics26.json` 记录 asa 的日语 `い→i` 和单音符英语 `hello→hel-/h e`；中文 `你` 及表情符号的 `can_convert=false`，`lyrics_apply` 仍返回成功、保留旧 `a` 音素并报告有效。两种输出保存重开未变，不等同正确转换；实际抛错回滚未见。详见 [默认值](../ai-note-defaults-26.md) 和 [歌词转换](../ai-lyrics-conversion-26.md)。

## 素材与验证

`artifacts/media-handle-26-349c07fdd1874a6c9e3fc24d73e16b33/receipt.json` 中已持有 DELETE 的目标句柄可重命名自身，候选句柄覆盖锁定目标失败；并未建立完整素材事务、原生刷新恢复或崩溃持久性。自动审查此前拦截的守卫保持原位，未绕行。

`artifacts/feature-acceptance-4768f923d99b/summary.json` 的 4 个相关功能用例及清理共 5 通过，涵盖生命周期、普通 VPR 编辑、无效音素素材与既有扩展守卫；独立 stdio 返回 0.18.0，无自有前台切换或遗留会话。两批结果分别记录，不相加为全量验收。本轮 Python AST 覆盖 91 个文件且无错误，操作目录检查通过；未改 C#，未重新构建。本对话 MCP 仍报告 Python 0.4.0、0 会话，原生宿主此前比对为 0.5.0。

下一步见 [TODO](../../TODO.md)。
