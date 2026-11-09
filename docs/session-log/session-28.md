# 会话 28：歌词/音素暂存隔离

日期：2026-11-10。起点提交：`0c56b2ecabe8414f3f96f43ffe6da8026321eb1f`。源码版本 0.19.1；完整目标继续进行。

## 修复和验收

旧版私有 AI 工程中的 `artifacts/feature-acceptance-0b599a61750f/lyrics_transaction28.json` 记录：先暂存 tempo 修改，再调用 `lyrics_apply`，成功或空歌词调用均提交了无关 tempo；原生失败后手动 rollback 则会一并撤销它。

`native/LibraryOperations.cs` 在 `lyrics_apply`、`phonemes_apply`、`lyrics_reset` 和 `phonemes_reset` 共用入口调用 `ScoreRequireUnstaged`，现有转换、提交及错误路径其余部分保持不变。`artifacts/feature-acceptance-c9c5f40275ad/summary.json` 的单项真实 MCP 用例及清理通过：四项操作在已有暂存时保持 tempo、音符、history、dirty 不变；手动清除暂存后正常日语歌词应用、保存及重开通过。原生失败后新产生的暂存是否完整回滚、`Commit(false)` 的撤销历史均未改变或证明。

主人要求除必要测试外不再做额外测试。收到要求后仅做构建前必要静态检查、一次 Release 构建和上述一项定向验收。Roslyn 覆盖 27 文件/208 引用、Python AST 104 文件及操作目录通过；构建为 0 警告、0 错误。新独立 stdio 为 0.19.1，未发生自有前台切换或遗留会话。

## 先前调查与后续

同一轮中，三个 `gpt-6.1-terra` 子 agent 在主人新要求前完成了有限调查。`artifacts/feature-acceptance-a8a508f71da6/compose_resolver28.json` 的候选规则在 asa 的 `い/か/きゃ`、`cat/CAT`、`ni/hao` 有观测正例，对多音节和不可转换样本提出错误；空候选分支、其他声库和语音正确性仍未证明。`artifacts/feature-acceptance-cba7992351b1/default_bootstrap28.json` 以已安装默认对在空 asa 片段引导日英中三个单音节并保存重开；该路径尚未接入生产。详见 [转换候选](../compose-resolver-28.md)、[默认引导](../default-bootstrap-28.md) 和 [事务证据](../lyrics-transaction-28.md)。

已审查拦截的扩展守卫未改变或绕行。自动音素转换、普通素材未知字段及设备/DAW 边界继续保留在 [TODO](../../TODO.md)。
