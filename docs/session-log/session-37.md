# 会话 37：多片段整体混缩超时

日期：2026-11-10。

## 用户要求

修复单段正常、多段工程整体混缩超时的 MCP 问题。保留原生引擎、私有桌面和原始工程保护。

## 原因与修改

`RenderNativePart` 原先在目标片段波形有效且收到其完成事件时便退出，然后调用整个序列的 `StopAsyncRendering` 并销毁 Lua 控制器。实际单段回执中目标已完成但 `finished=false`；其他片段仍在队列中，后续整体混缩出现 `second_end=68`、`finished=true`、没有有效目标波形，等待到 120 秒超时。

修改 `native/EngineSession.cs`：成功退出必须同时满足目标波形有效和整个序列渲染完成。超时信息增加片段名称、started、completed 和 valid_wave，便于区分队列停止与混音阶段。未修改原生或 Python 超时值，没有添加重试或替代合成后端。

`tools/verify_features.py` 新增同轨两段用例和可指定 `--mixdown-fixture` 的实际 VPR 用例。实际用例先导出单段，再混缩全工程，并通过原生 tick-to-seconds 映射检查每段非零样本。音频读取默认仍限 30 秒，实际工程用例显式允许 600 秒。

## 验证

| 回执 | 结果 |
| --- | --- |
| `artifacts/feature-acceptance-fa3bc09c40ea/summary.json` | 旧实现的短同轨两段测试通过，未复现问题。 |
| `artifacts/feature-acceptance-1f0384208023/mixdown.project_fixture.json` | 实际 12 段工程：单段 0.750 秒成功；整体混缩 120.032 秒后在原生片段渲染阶段超时。 |
| `artifacts/feature-acceptance-bad611ebf304/summary.json` | 修复后已生成完整混缩 WAV；验收因原有 30 秒读取上限拒绝约 65 秒文件而失败，保留此回执。 |
| `artifacts/feature-acceptance-e83d8be0e2a2/summary.json` | 修正用例读取边界后，实际工程用例与会话清理通过；没有传输错误。 |

最终单段调用 0.829 秒，随后混缩 0.203 秒。输出 `output/feature-e83d8be0e2a2-002-fixture-mix.wav` 为 65.142857 秒、2,872,800 帧、44100 Hz、24 位双声道，12 个片段逐段峰值均非零。此耗时包含先单段导出已完成的整条渲染队列，不作为冷启动混缩性能指标。

原生语义预检 32 文件 / 211 引用零错误；Release 构建通过；修改的 C# 和 Python 文件无编辑器诊断。没有运行全量套件。

## 交付边界

测试源 `output/lucifer_ctrl_names_probe.vpr` 只读打开，未覆盖。只操作测试自有私有宿主；其他客户端和用户交互式编辑器保持原样。当前聊天未暴露 VOCALOID MCP 工具，验证通过独立真实 stdio MCP 连接完成，不称为当前聊天绑定验收。

版本保持 0.27.0、39 工具、127 操作。活动宿主加载的是启动时的程序集副本；保存并关闭其工程后重启 `vocaloid6-native`，或调用 `vocaloid_runtime restart`，才能使用新构建。未提交既有或本次工作树修改。