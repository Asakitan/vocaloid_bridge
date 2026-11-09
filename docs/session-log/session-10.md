# 会话 10：扩展拆合、跨工程迁移与输入错误

日期：2026-11-10。起点提交：`244df5f`。本轮交付 0.5.0；总目标继续进行。

## 目标与分工

继续 AI 声库的后台原生 MCP，不启动经典试用，不接管用户编辑器。主线处理 MIDI 输入错误，子 agent 分别调查并实现扩展数据拆合、跨工程迁移和 DAW IPC 隔离；结果在统一构建和测试前均视为候选。

## 当前进展

对照 Microsoft WinMM 文档与本机 SDK 头文件，已编写输入错误通知、回调异常及队列溢出时的提交保护；`MIM_MOREDATA` 按有效 MIDI 短消息处理并记录积压计数。统一构建 0 警告、0 错误；`artifacts/midi-callback-b0fae6312bd4.json` 验证已构建回调分类和提交前检查，未打开 MIDI 硬件，实际驱动的通知、并发与设备清理仍待验证。

静态审阅发现：带未知实体扩展的源工程经私有剪贴板复制到无扩展目标时，原有检查仅看目标，可能丢失源扩展。`artifacts/feature-acceptance-fb8cedfece70/summary.json` 的红测确认此前粘贴未被拦截；先增加源快照检查与剪贴板清除时的观察器释放，再调查原生身份映射及回滚策略，后续成功迁移的证据见下。

同一 `artifacts/feature-acceptance-a4a1a5dc7d8d/summary.json` 记录带未知字段的音符与片段分割/连接、冲突回滚、撤销重做和保存重开，以及 MIDI 事件流与清理，共 5 项通过；这不是完整历史套件重跑。另一私有剪贴板身份探针触发 `0xC0000005`，没有有效身份回执，不能据此声称跨工程扩展迁移完成。

静态追踪显示两款插件的已观察请求/通知管道路径使用相同固定名称；VSTi 某条共享映射路径则含进程 ID。私有 desktop 不足以证明管道隔离，本轮未加载插件或接触真实端点；详见 `docs/daw-ipc.md`。

后续跨工程粘贴改为保留独立快照中的明确源实体，并与目标原生 Duplicate 返回对象逐一配对；为目标新增身份跟踪初始化及失败撤销。不透明额外资源仍要求明确冲突规则。`artifacts/feature-acceptance-d26fff138fbe/summary.json` 保留旧保护下的迁移红测；新代码和历史边界的验证见下。

第二批构建为 0 警告、0 错误。`artifacts/feature-acceptance-a21669fbf03f/summary.json` 中普通剪贴板、身份历史、音符/片段拆合及资源保护通过，两个新迁移测试在撤销到空工程时因测试直接索引 `tracks` 而报 `KeyError`；原生空工程输出省略该字段。已修正两处测试读取，保留失败回执并定向复验。

`artifacts/feature-acceptance-b8c01e2d4375/summary.json` 的两个定向用例及清理共 3 项通过：AI 轨道、片段、音符扩展经剪贴板跨工程迁移，支持偏移、源关闭、剪贴板清除、保存重开与撤销/重做；普通目标已有编辑历史可跨首次扩展粘贴回到旧历史并重做，新分支清空 redo。不透明额外资源及未知数组仍有保护边界，不能据此断言所有格式组合通过。

`artifacts/probe-appcontainer-native-child.txt` 使用随机合成管道、私有 desktop 和无窗口进程；普通子进程可连接，受限子进程确认 AppContainer 令牌且返回 Win32 错误 5，临时 profile 删除返回成功。此结果仅证明该合成管道在本机默认权限下的观察，未验证实际插件或所有 IPC。

带实体字段的剪切先登记独立快照，再用原生事务移除源实体并同步历史；若提交结果不确定，保留剪贴板快照供检查。`artifacts/feature-acceptance-4cb5b47a3915/summary.json` 覆盖音符、片段、轨道剪切与跨工程粘贴，2 项通过含清理。

`project_merge` 复用扩展实体迁移及目标历史事务；导入源的 root/master 未知字段和不透明额外资源在变更目标前报错。剪切和合并的旧保护红测分别为 `artifacts/feature-acceptance-4f793d54a771/summary.json`、`artifacts/feature-acceptance-cf65a50968ff/summary.json`。最终相关构建 0 警告、0 错误，`artifacts/feature-acceptance-e57fec059ac3/summary.json` 中普通剪贴板/合并、扩展迁移、旧历史、剪切、合并及清理共 7 项通过。目标已有根字段、主轨字段与额外资源的粘贴回归见 `artifacts/feature-acceptance-288f3f9a90b8/summary.json`。

源工程带不透明资源时，扩展剪切曾先移除实体而后续粘贴报错，红测保留于 `artifacts/feature-acceptance-fdeed6a511d6/summary.json`。增加剪切前资源检查后重新构建为 0 警告、0 错误；`artifacts/feature-acceptance-adac1d5901d0/summary.json` 的资源保护、正常扩展剪切与清理共 3 项通过。

本对话 MCP 连接先前返回 `Transport closed`，后续状态查询成功且工具目录显示 37 项，但运行中的 Python MCP 版本仍为 0.4.0；0.5.0 通过新建的独立 stdio 连接做定向验证。未为刷新版本而重启客户端或用户编辑器。
