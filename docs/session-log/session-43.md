# Session 43: 临时文件自动清理

日期：2026-11-11

## 目标

`output/` 和 `.runtime` 里累积了大量测试工程、渲染 WAV 和已退出宿主的 stderr 日志。加入自动清理：修改时间超过 1 小时的文件按临时文件处理，避免继续堆积；清理范围不碰用户原始工程，也不碰 `.runtime` 里的手册、素材库、宿主副本等数据。

## 修改

- `vocaloid_bridge/cleanup.py`：新增有界清理实现。
  - 范围：`output/**`、`.runtime/mcp-temp/**`、`.runtime/tmp/VocaloidBridge-<guid>/**`、`.runtime/VocaloidBridge-<guid>.stderr.log`。
  - 年龄：默认 3600 秒；`VOCALOID_TEMP_MAX_AGE_SECONDS` 可调，允许 60 秒到 30 天。
  - 活动宿主判定：临时命名空间只有对应 stderr 日志可删除时才整树清理。运行中的宿主持有日志句柄，Windows 返回共享冲突，日志和目录都保留。
  - 安全边界：不跟随 reparse point，不删除根目录，不碰 `.runtime` 的其他内容；单个失败只记录，不中断整轮。
  - 回执：`.runtime/temp-cleanup/last-report.json`（apply）或 `last-dry-run.json`（dry-run），包含扫描数、候选数、删除数、字节数、保留原因和失败。
  - 并发：apply 使用 `.runtime/temp-cleanup/sweep.lock`，10 分钟视为过期，避免两个服务同时清理。
  - 线程：`start_background_sweep` 在服务启动时运行一次，之后默认每 600 秒重复；`VOCALOID_TEMP_CLEANUP=0` 关闭，`VOCALOID_TEMP_CLEANUP_INTERVAL_SECONDS` 调整周期。
- `vocaloid_bridge/server.py`：启动时开启清理线程；`vocaloid_status` 增加 `temp_cleanup`，返回最近一次 apply 回执的摘要。
- `tools/clean_temp_output.py`：手动入口。默认 dry-run，`--apply` 删除，`--max-age-minutes` 和 `--keep GLOB` 可调；`--json` 输出完整回执。
- 版本升到 0.28.0；工具数量和结构化操作数量不变（39 / 127）。

## 验证

- 独立假工作区自测（`.runtime/cleanup_selftest.py`，验证后删除）：
  - 新旧文件、嵌套 `output`、`mcp-temp`、活动/已退出宿主命名空间和单独 stderr 日志。
  - dry-run 只统计候选，不删除任何文件；apply 删除 6 个文件 / 1 个目录 / 66 字节。
  - `keep-me.vpr` 被 `--keep` 保留；活动宿主的命名空间和较新的日志保留；`.runtime/keep.txt` 不动；第二次 apply 为 0。
  - `summary()` 返回同一回执。
- 真实工作区 dry-run：4573 个候选 / 5,503,881,176 字节，保留 14 个一小时内项，失败 0。
- 真实工作区 apply：删除 4573 个文件、5 个空目录、5,503,881,176 字节；保留 14 个（13 个一小时内渲染文件和 1 个活动宿主日志），失败 0。清理后 `output/` 只剩最近一小时的 13 个文件。
- `python -m compileall -q vocaloid_bridge tools/clean_temp_output.py` 通过；导入 `vocaloid_bridge.server` 后 `temp_cleanup.summary()` 返回同一回执。

## 未完成 / 已知边界

- 自动清理会在服务启动时和之后每 10 分钟删除 `output/` 中超过一小时的所有文件，包括本机试听用的旧渲染；用户原始工程在 `output` 之外，不受影响。
- 没有重跑全量功能验收；客户端需要重新连接才会载入 0.28.0 的 `temp_cleanup` 字段。
- 清理不回滚；回执只记录有界样本，完整数量以汇总字段为准。
