# 会话 27：JSON Patch sidecar 迁移与 AI 转换观察

日期：2026-11-10。起点提交：`229c2e2052af787c8e91f472d2430d54579cc0cf`。源码版本 0.19.0；完整目标继续进行。

## JSON Patch 与无效音素身份

三个 `gpt-6.1-terra` 子 agent 分别调查补丁 sidecar 身份、原生歌词转换及原生新建音符。`artifacts/patch-sidecar-27-9dda41d946cb4cfe856b7b9c79a7b694/receipt.json` 在普通合成 VPR 中复现旧补丁对同字段异身份的插入、删除、移动、复制、替换和轨道移动造成 sidecar 错绑。`artifacts/feature-acceptance-f428a8882714/summary.json` 的独立原生观察发现复制无效音素音符后，原音符仍为 false、副本变为 true。`artifacts/feature-acceptance-2212e75bc34a/summary.json` 是新契约的旧版真实 MCP 红基线。

`vocaloid_bridge/projects.py` 先验证源 sidecar，再在私有 JSON 副本上顺序应用实际 `jsonpatch` 操作，跟踪受引用音符的 Python 对象身份。移动迁移索引，复制生成独立 sidecar 条目，删除或替换移除旧条目；位置、时长和音高更新对应签名，歌词/音素/语言变化仍受保护。未改变 sidecar 时保留原 bytes，改变时保留受测未知字段并重写 sidecar。文件级 note-tree 补丁继续检测受审查的 controller、轨道自动化及 direct-pitch-item 扩展；未修改原生守卫或操作受保护扩展工程。

`artifacts/feature-acceptance-840e52ca3977/summary.json` 的 1 个定向用例及清理通过，覆盖复制音符/轨道、轨道移动、删除、替换、位置/时长/音高、真实原生打开保存重开、原资源及 sidecar 未知字段。`tools/check_patch_semantics_27.py` 另在内存验证多引用、连续复制、临时子树、根复制、跨片段移动、数组插入、转义路径、失败原子性和守卫谓词；不等于原生历史或所有补丁组合。

## 回归失败与自有素材清理

`artifacts/feature-acceptance-daac15c8755e/summary.json` 为 5 通过、1 失败：旧 `library.media_invalid_phoneme` 用例仍要求音高补丁被拒。该断言未执行后续素材删除，生成的自有 clip `748f5c70-f6f9-453a-8b8c-640358865ad1` 经 ID、名称及绝对路径核对后，通过独立私有原生 `media_delete` 清理。

专用原生保存重开证明位置/时长/音高改变时 invalid 标记仍为 false，随后更新旧用例为音高正例及歌词改变拦截，并用 `finally` 保证其自有素材清理。`artifacts/feature-acceptance-0f1de36b3862/summary.json` 的该用例及清理通过。失败和后续证据均保留，批次不相加为全量通过。

## 原生 AI 转换与边界

`artifacts/feature-acceptance-081dbbadce90/lyrics_native27.json` 的 asa 双音符样本中，中文 `ni hao` 得到 `n i` / `x AU`；`你好`、`ni3 hao3` 和一些不可转换输入仍可能沿用旧音素，即使操作返回成功。`artifacts/feature-acceptance-b3983340ab31/native_note27.json` 中，`note.add` 的 `こんにちは` 只生成 `こ/k o`，emoji 沿用 `a`；日语 `い` 的显式/省略音素及渲染通过，但英语/中文缺少同语言上下文。未证明听音、所有语言、原生失败后回滚或通用自动转换。

本轮 Python AST 覆盖 97 个文件且无错误，操作目录检查通过；未改 C#、未重新构建。新独立 stdio 报告 0.19.0；此前本对话旧连接报告 Python 0.4.0、0 会话，原生宿主此前比对为 0.5.0。具体边界见 [补丁身份](../patch-sidecar-27.md)、[歌词观察](../lyrics-native-27.md)、[音符观察](../native-note-27.md) 和 [TODO](../../TODO.md)。
