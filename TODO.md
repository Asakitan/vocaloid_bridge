# 当前目标

补齐 VOCALOID6 的后台原生可调用功能，保留创建、打开、编辑、保存。用户选择仅用 AI 声库，保留经典源工程保护但不安装经典试用。目标继续进行，剩余环境和扩展格式边界不冒充完成。

## 当前进展

- 0.4.0：37 工具、125 个结构化操作；默认新建 AI 人声轨。
- 未知 VPR 字段、固定嵌套对象、额外资源及轨道/片段/音符复制的定向回归通过。
- MIDI 六操作通过显式事件流和静音 transport 测试，真实硬件尚未验；详细回执见 STATUS。

## 立即下一步

1. 为带未知实体数据的 split/join 设计切割前后的身份迁移与冲突规则；继续处理剪贴板、合并及非实体数组，保持源数据保护。
2. 处理 WinMM `MIM_ERROR` 通知并用独立 MIDI 输入源验证硬件录制、故障和关闭清理；现有两个 CubaseAI 端口保持未打开。
3. 调查 DAW 宿主的 IPC 隔离后再进行真实宿主同步；实际听音质量尚未人工确认。
4. 既有客户端重新连接 `vocaloid6-native`；本对话旧连接曾返回 `Transport closed`，不操作用户前台窗口。

## 验证约定

使用 `tools/verify_all.py` 选择与新改动相关的 case，`tools/generate_operation_catalog.py --check` 检查契约。保留原失败记录和后来修复证据；不把多次定向计数相加为全量通过。内部 44100 Hz 合成与独立输出采样率分开记录。

## 历史索引

- [会话 06](docs/session-log/session-06.md)：108 操作和历史整合结果。
- [会话 07](docs/session-log/session-07.md)：0.2.1、Robot、PPSF3、完整性保护。
- [会话 08](docs/session-log/session-08.md)：0.3.0、设备传输、冻结、未知数据保留。
- [会话 09](docs/session-log/session-09.md)：0.4.0、AI 默认轨、扩展复制、MIDI 事件流。
