# 会话 25：源工程一致性与轨道字段 no-op

日期：2026-11-10。起点提交：`0a2c493af352777158f068811416831035c1e25c`。源码版本 0.17.3；完整目标继续进行。

## 源工程版本一致性

此前 `ProjectStore` 分别打开源 ZIP 读取序列和复制其他成员。在自有合成 VPR 中强制独立进程替换源后，`artifacts/source-snapshot-25-cdvpdpa1/receipt.json` 记录输出 A 版序列与 B 版资源及 ZIP 注释的混合；先存写句柄也未阻止编辑。

`vocaloid_bridge/projects.py` 使用 Windows 只共享读取的单个源句柄，从读取序列到复制全部成员及关闭独立输出都持有同一个 ZIP 视图。`artifacts/source-snapshot-25-uvxy01h9/receipt.json` 验证测试中的并发原位写入/替换受到限制、释放后替换成功、先存写句柄在输出创建前被发现、参数校验失败后句柄释放。测试曾因 `pywintypes.error` 类型未识别而中断，修正测试后通过。`write_copy` 接受调用者自己提供的 data，不承诺该数据与调用时源版本相同；远程文件系统、所有映射、崩溃及路径竞争未穷举。详见 [源一致性](../source-snapshot-25.md)。

## 轨道字段和录音

旧宿主 `artifacts/feature-acceptance-81a85f628a55/summary.json` 观察颜色、静音、独奏、总线和 MIDI 录音同值更新会置脏。修改后的 `track.update` 仅在名称、颜色、静音、独奏、总线所有给定值相同且未提供录音字段时提前返回；仍验证原生暂存状态及入口守卫。录音字段保留 setter。另一个旧宿主结果 `artifacts/feature-acceptance-e4e3e4128287/summary.json` 显示 `midi_recording=true` 重开后恢复 false，持久语义尚未确认；同时受测实际名称、颜色、静音和独奏保存成功。

## 音符和素材调查

三个 `gpt-6.1-terra` 子 agent 分别研究普通音符原型、合成素材锁和轨道无变化行为。`tools/check_file_note_identity_25.py` 的合成红基线观察旧音符 A/B 和新音符输出未知标记 A/A/A，B 的 velocity 也继承 A；生产音符行为尚未修改，身份和默认值策略仍待验证，见 [音符调查](../file-notes-25.md)。

`artifacts/media-atomic-25-a5cd2aa12cbf4df5b0d324e8692fc427/receipt.json` 中字节锁未阻止测试写法先截断文件，只读共享句柄下竞争写入和替换失败。原生素材刷新恢复、通用合并与崩溃持久性尚未验证，见 [素材探针](../media-atomic-25.md)。所有先前自动审查拦截的扩展守卫均保持原位，未通过其他路径绕行。

## 验证与客户端

构建前 Roslyn 覆盖 26 个 C# 源文件及生成的全局 using、208 个引用，Python AST 覆盖 86 个文件，操作目录检查通过。唯一一次 Release 构建 0 警告和 0 错误。

`artifacts/feature-acceptance-3fc96299dad5/summary.json` 的 8 个定向功能用例及清理共 9 通过，覆盖创建/打开/编辑/保存、轨道实际改动和 clean/dirty no-op、文件事件和既有扩展守卫。独立 stdio 报告 0.17.3，无自有前台切换或遗留会话；本对话既有 MCP 连接仍报告 Python 0.4.0、0 会话，原生宿主此前比对为 0.5.0。未执行全局刷新。

下一步见 [TODO](../../TODO.md)。
