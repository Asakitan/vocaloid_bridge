# Session 49: 全套验收与扩展工程录音

日期：2026-11-14。

## 目标

核对 V7 VMM、片段效果、原生变声及 AI DVQM 的实际边界，执行受维护全套验收并修复暴露的可操作缺口。使用隔离宿主及自有工程，不操作交互编辑器或覆盖原始素材。

## 当前结果

- 先前修复后按同一批本地夹具重跑 V7 全套：143 通过、42 失败、1 阻塞、2 跳过，含清理；41 个工具均有通过用例中的正向调用，但 8 个媒体操作及 3 个标准轨 Singing Skill 操作没有正向通过。回执 `artifacts/feature-acceptance-de3baf6e9e5d/summary.json`；自动临时文件清理在此次运行中关闭，外部多片段工程夹具仍缺。后续 Breath 和 VoiceColor 测试修改尚未重新运行全套。
- Breath 用例改为 V7 全新工程、同代 GekiyakuV 声库和轨道作用域。V7 受测句的开关及气息量有 PCM 差异，但 Often 与 Rarely 无差异；Rarely 保存重开后参数仍正确、音频仍相同，频率差异断言失败，`artifacts/feature-acceptance-14556982650d/summary.json`。V6 原路径与音频断言通过 `artifacts/feature-acceptance-366540d779ee/summary.json`。单句样本不足以证明 V7 频率永不生效，原因待查。
- VoiceColor 测试原先在 V7 未传轨道作用域，并尝试对 AI 轨写入标准轨参数；现改用 V7 原生工程、同代声库和适用性标记。GekiyakuV 的四类 `S5Expression`、`S5Air`、`S5Character`、`S5Attack` 及旁路在受测短句均有 PCM 差异，V7 `artifacts/feature-acceptance-69705fa877b9/summary.json`；保留原 V6 片段级回归并通过 `artifacts/feature-acceptance-8aefac3f9629/summary.json`。未验证所有声库或主观听感。
- 带本地 VSQX3/4、PPSF2/3 及官方手册文本的一次 V7 全套基线：133 通过、48 失败、1 阻塞、2 跳过，含清理；无传输错误、遗留会话或自有前台切换。回执 `artifacts/feature-acceptance-5c183883d42f/summary.json`。其中部分失败来自 V6 专用作用域、不支持的 V7 原生接口或旧守卫预期，不可把它们合并为通过；多片段真实工程夹具未提供。
- 全套前修复生命周期验收误认为宿主必须从零代启动，并按 V7 轨道作用域设置声库；前置生命周期用例后再执行验证通过，V7 `artifacts/feature-acceptance-eb3e327e743b/summary.json`。
- 操作目录验收比较生成目录的操作名与契约行，允许服务按产品补充说明；130 项目录定向通过，V7 `artifacts/feature-acceptance-0584d924f85d/summary.json`。
- MIDI 录音原先一律拒绝带实体扩展的工程。现有音符插入使用 `note.add` 的归档事务和身份检查；提交前拒绝同形音符造成的归档身份冲突并回滚，未获支持的曲线变更仍受原有守卫限制。V7 `artifacts/feature-acceptance-2099b6561503/summary.json`、V6 `artifacts/feature-acceptance-6be3fa3178a3/summary.json` 通过冲突回滚、合成事件流、已有音符/音高/控制器/自动化扩展、附加资源、保存重开及撤销重做；未验物理 MIDI 设备。冲突保护前的意外成功基线为 `artifacts/feature-acceptance-2a92a14a5583/summary.json`。
- V6/V7 原生语义预检各 35 文件、218 引用、零错误，专属 Release 宿主均构建成功；V6 同批生命周期及目录定向通过，见 `4661a69734e4`。
- 全套入口补入原本遗漏的作曲流程和 V7 控制验收；V7 `artifacts/feature-acceptance-b7f9a143fc21/summary.json` 覆盖 `vocaloid_workflow`、`project_ai_adjust`、直接 `ai.status/generate`、batch 和音高固化。普通原生工程的暂存保护、音素时值及批量音符用例通过：V7 `925c506eb798`、V6 `ccaf2d9aae12`；扩展工程离线反转的产品后端归属及源数据保护通过：V7 `b54a63201afe`、V6 `24e361fb26fb`。
- 私有样式用例改用 V7 轨道作用域和真实 Take 模型；捕获、更新、应用、效果、撤销重做、保存重开和自有样式清理通过：V7 `b703e55eb213`、V6 `8dd41f7beddc`。
- [官方 V7 升级说明](https://d2d1pbdkm53nop.cloudfront.net/en/learn/ln7005/) 将 MEDIA 与 VOCALO CHANGER 列于移除或弃用项，并说明前者可通过音频和序列文件导入，后者使用另售插件。[V7 7.0.0 英文手册](https://rsc-net.vocaloid.com/assets/pdf_files/cc/VOCALOID_Reference_Manual_ENG.pdf) 第 60 页的音效窗口段落提到选中轨道或片段；但本机 V7 7.0.0.1 的 `WIVSMPart` 无效果管理器，`WEffectManagerExtension` 和效果选择器仅绑定轨道或主轨。该文字不足以证明独立片段效果存在，桥接替代实现仍未验证。
- 在 V7 7.0.0.1 私有原生宿主中使用同代 GekiyakuV 7.0.0：轨道 `S5Attack` 从 0 改到 100，前后 198450 帧非静音 WAV 差值 RMS 为 0.01125779；音符 HMM、撤销重做、保存重开与声库身份保持。V7 回执 `artifacts/feature-acceptance-605da3f66ac3/summary.json`；没有主观试听。
- 同代产品独立 DVQM 探针：V7/GekiyakuV 与 V6 6.13.3.1/asa 6.3.0 分别创建普通 AI 工程，音符 HMM `37/91`、时值 73 正常重开；人工向副本音符加入非空旧 Attack 后，原生加载读出 `0/0`、时值 160，保存省略 `singingSkill`。先 DVQM 后 HMM 的内存值恢复但撤销得到 `64/64`，保存重开仍 `0/0`；先 HMM 后 DVQM 立即得到 `0/0`。两种原生 setter 均返回成功，不能据此证明持久化安全；桥接守卫保留。V7 `605da3f66ac3`、V6 `c0cbacbfa685`。早期 V7 引擎样本使用 V6 asa 声库，不再作为纯 V7 声库证据。
- 安装版 V7 `WAudioEffectManager` 的效果块枚举仅有 Master、Track、Converter；未观察到片段块托管入口。用户级制作 SKILL 已纠正版本路由、音符 HMM 与轨道 Singing Skill、`S5Attack` 与旧 DVQM 的区别，以及 V7 桥接 WAV 反转支持。

## 尚未完成

全套复测未因后续定向结果而改写；其余失败尚需逐项区分夹具、产品限制和实际缺陷，V7 Breath 频率音频断言仍未通过。V7 VMM、片段效果、原生变声及 AI DVQM 无损原生写入仍未实现；当前聊天未暴露 VOCALOID MCP 工具，独立 stdio 验收不等于客户端已重连。