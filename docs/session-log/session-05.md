# 会话 05：补齐剩余原生能力

日期：2026-11-10。

## 目标

补齐功能矩阵中剩余的高级表现、自动化、传统格式、静态音素表和特殊素材捕获；维持私有桌面、原件保护和原生后端约束。

## 当前进展

- 已补齐非零起点音频素材捕获，依据原生时间映射物化私有 WAV；跨速度变化的 PCM 逐帧比较、导入和保存重开通过，回执 `artifacts/feature-acceptance-4e5a7b5806c7/summary.json`。
- 五种语言的静态音素表通过 `project_library` 提供；来源为官方 V6.13.0 手册，响应明确标注不是原生动态枚举，逐符号核对回执为 `artifacts/feature-acceptance-00c3bf08921e/summary.json`。
- 新增原生轨道音量、声像和主音量自动化；事件保存重开及实际 PCM 混音分别在 `artifacts/feature-acceptance-4d341970430a/summary.json`、`artifacts/feature-acceptance-6e1b905dc259/summary.json` 通过。
- AI 次声库素材捕获、导入、保存重开通过，回执 `artifacts/feature-acceptance-cd7113488f36/summary.json`。原生 VMM 保存字段但读回为空，桥接层从原生素材 JSON 读取并标注来源。
- VSQX 4 使用 Yamaha 公开示例，VSQX 3 使用公开项目测试文件；独立 XML 解析与原生导入、VPR 重开后的音符、歌词和音素一致，回执 `artifacts/feature-acceptance-6609879d4a29/summary.json`；源轨道与声库身份尚未完整验证。
- Robot、Breath、Take、VoiceColor 和 MIDI 旁路提供原生读写，参数与重开回执 `artifacts/feature-acceptance-84721c900e94/summary.json`。Robot 脚本在片段渲染和混缩前恢复，真实 WAV 回执 `artifacts/feature-acceptance-23de638ffae9/summary.json`。
- 初始化声库服务后，原生 DVQM 目录实际为 36 个 Attack 和 42 个 Release；此前零条结果来自初始化前查询。传统及 AI 各一组 Attack/Release、无效音素素材捕获和重开定向通过，回执 `artifacts/feature-acceptance-ad57c0d13e39/summary.json`。
- 无效音素标志与 AI Attack/Release 在桥接自有 `.vsclip` 中使用显式扩展；无效音素在 VPR 使用桥接 ZIP 条目。文件级 VPR 修改保留扩展，若引用音符发生不匹配则拒绝写出，回执 `artifacts/feature-acceptance-093eeb824ba9/summary.json`。
- CBC RADIO 公开的 PPSF V2 样本保存于私有 `.runtime`，来源 `https://radichubu.jp/radio_miku/contents/id=41671`。原生导入的 497 个音符在 VPR 重开后保留，但四条传统轨变为 AI 轨且声库 ID 丢失，失败回执 `artifacts/feature-acceptance-d6d8e5677578/summary.json`。PPSF V3 未验；不把此样本标为无损通过。
- 完整 MCP 验收使用本地手册及 VSQX3、VSQX4、PPSF V2 实际样本，结果 60 通过、1 失败，回执 `artifacts/feature-acceptance-da32b0217fce/summary.json`。35 个工具及 91 个结构化操作有成功调用；无传输错误或遗留会话。用户前台有切换，测试进程未抢占前台。
- 其他特殊素材及未验接口继续逐项核对；没有实测证据的功能不标为完成。