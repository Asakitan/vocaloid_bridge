# 当前目标

补齐 VOCALOID6 原生后台 MCP 的全部可调用功能；保留创建、打开、编辑、保存。无前台操作、无替代后端。目标仍在进行。

## 已完成增量

- 0.2.0：36 个工具、108 个结构化操作的发现目录与原生调用；新增批量音符、颤音、时序、回滚、Singing Skill、HMM 权重、私有样式管理。
- 私有构建快照与每宿主 VSM 缓存隔离；音频导入/克隆初始化修复。
- 整合回执 `artifacts/feature-acceptance-012574702338/summary.json`，后续定向修正见 STATUS。

## 当前问题及下一步

1. 修复经典 VPR/PPSF/VSQX 保存/重开后的 track type 与 voice ID 丢失；不要替换源声库，不要用 metadata 宣称原生修复。
2. 定位 Robot 返回 NoError 但 PCM 相同的原因；核对 VLC 与唯一 VSM app ID 的真实关联，尚未证实关联就是根因。保持多宿主缓存隔离。
3. 复核改变 sample_rate/bus_no 后的组合渲染；已验证参数持久化不等于该组合发声通过。
4. 取得 PPSF V3 实际样本后运行其用例；设备/DAW 行为另需真实环境。

## 验证

`tools/verify_all.py` 是整合入口；`tools/generate_operation_catalog.py --check` 检查操作目录。只针对新改动或具体失败运行必要验证，不重复已通过的未变用例。所有测试只在私有 desktop；保留实际失败证据。

## 历史索引

- [会话 05](docs/session-log/session-05.md)：旧 60/1 基线。
- [会话 06](docs/session-log/session-06.md)：本轮实现、通过、失败与接续。
