# Session 38: 样式与细项参数修复

日期：2026-11-10

## 目标

修复 MCP 的样式保存和细项参数应用；保留既有修改，所有工程检查使用私有原生引擎及 output 内的新文件。

## 定位

现有私有样式验收只比较音频效果链，没有检查来源声部的样式关联及省略 bypass 时的参数应用。按“保存样式关联来源声部；调节参数默认启用对应效果，显式旁路优先”修复。用户未提供具体失败调用或参数名。

## 修改

- `style_capture` 在保存原生预设后，以原生事务写回来源声部的名称和 ID；拒绝既有暂存编辑。工程撤销不撤销独立的预设文件。
- `performance.set` 的 Robot、Breath、Take、VoiceColor 参数默认启用对应效果；同次请求显式 bypass 优先，不启用未修改的效果。
- `style_apply` 复用音频暂存核心，将 MIDI、音频链和身份统一提交，支持一次撤销。
- 样式捕获和应用接入原有扩展字段身份事务；不变曲线与数组继续校验，显式替换效果采用既有规则。
- 操作目录、模块文档、状态和作曲指引同步；接口数量及包版本保持 39 / 127 / 0.27.0。

## 验证

- `artifacts/feature-acceptance-d811b54254b7/summary.json`：显式解除旁路、另一个目标声部的往返基线通过。
- `artifacts/feature-acceptance-1ee00aa27368/summary.json`：来源未关联、效果仍旁路两项失败，source_linked=false、voice_color_enabled=false。
- `artifacts/feature-acceptance-85d656169aa9/summary.json`：第一步来源关联和自动启用修复通过。
- `artifacts/feature-acceptance-311dce7269c6/remaining.private_styles.json`：最终普通样式路径通过，覆盖四类参数、显式旁路、单步撤销/重做及保存重开。同批扩展夹具重复添加模板已有 Gain，准备阶段失败；不是扩展样式功能结果。
- `artifacts/feature-acceptance-946acadda473/summary.json`：修正夹具后扩展样式及清理通过；保存重开、撤销/重做、root/track/part/note/tempo 与 MIDI/音频效果未知字段保留，原始 VPR 字节不变。

原生语义预检 32 文件 / 211 引用零错误，Release 构建通过，改动的 C# 与 Python 文件零编辑器诊断。操作目录生成通过，未运行全量套件，未新增声音差异或主观听音验收。

## 交付

当前聊天没有直接暴露的 VOCALOID MCP 工具，以上来自独立真实 stdio 会话。旧客户端需保存并关闭工程，再重新连接 MCP 或调用 vocaloid_runtime restart 载入原生修复。没有重启其他客户端、接管交互编辑器、覆盖用户原件或提交 Git；原有未提交改动保留。交接：`.vscode/handoff/style-38.md`。