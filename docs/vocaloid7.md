# VOCALOID7 兼容说明

## 选择与构建

0.29.0 支持本机 VOCALOID6 和 VOCALOID7，构建统一使用 .NET 10 Windows Desktop。`tools/setup.ps1` 默认根据注册表、Program Files 目录及核心 DLL 的实际文件版本选择最新安装；运行时每个新宿主使用同一选择器。活动宿主固定产品、版本及路径，不在工程中途切换。

`VOCALOID_INSTALL` 或 `setup.ps1 -Install` 可明确覆盖目录。`-Product` 用于校验选择结果，不会忽略已发现的目录另找同名安装。发现不支持的更新产品会报错，不能据此承诺未来 VOCALOID8 自动兼容。

```powershell
pwsh -NoProfile -File tools/setup.ps1
pwsh -NoProfile -File tools/setup.ps1 -Install 'C:\Program Files\VOCALOID6\Editor' -Product VOCALOID6
```

产品输出是 `native/bin/Release/<product>/net10.0-windows`，中间文件也按产品分开。标记绑定产品、核心程序集、安装目录、版本、框架和宿主摘要。缺失、过期或错误产物会提示 setup，不启动旧 DLL。安装更新后重新构建，再保存关闭活动工程、重连 MCP。注册名 `vocaloid6-native` 和既有任务标签保持兼容。

## 行为差异

| 范围 | VOCALOID6 | VOCALOID7 |
| --- | --- | --- |
| 声库、样式、表现、Singing Skill | 片段级 | 显式 `scope="track"`，影响整轨 |
| 声库身份 | 片段 `aiVoice`/`voice` | 轨道 `voice` 与 `voiceTypeID` |
| AI 类型初始化 | 原有行为 | 打开/克隆/导入时，只为空类型补同声库原厂默认值，返回 `initialized_voice_types` |
| 颤音 | `ai_enabled` | `curve_model`，支持值由 `vibrato.get` 返回 |
| Take | `take_lane` | `take_number`，使用原生范围 |
| VMM 素材库 | 保留 | `media_*` 明确不支持 |
| 音频效果 | 主、轨道、片段 | 主、轨道；片段级明确不支持 |
| WOR 反转/变声 | 保留 | `reverse`/`voice_change` 明确不支持 |

文件级编曲优先使用 V7 轨道 `voice`，兼容旧片段 `aiVoice`；新 V7 音符使用 `vibrato.aiCurveModel`，显式源音符保留原有字段。原生加载及保存仍核对轨道数量、类型和声库 ID，未知字段与资源继续由原有归档保护管理。旧 V6 工程在同轨使用不同片段声库时，无法无损映射为一个 V7 轨道声库，身份不一致会被拒绝。

原生 `MidiAi`、声库 `IsAi` 和编辑器面向用户的轨道名称不作未经验证的等同。实测 V7 引擎能用已安装 V6 asa 完成当前模板的合成；这不是全部旧声库或轨道组合均已验收的保证。

## 本机证据

- V6 6.13.3.1、V7 7.0.0.1：语义预检和分开构建通过。
- V7 默认选择：真实 stdio 编曲、自动音素、保存重开、374850 帧非静音 WAV，通过；`artifacts/background-demo-b575e1fb9f.json`。
- V6 显式覆盖：同流程 374849 帧非静音 WAV，通过；`artifacts/background-demo-603fccdd6a.json`。
- 新 V7 asa `BXHPECHANDRW3XEL`：新建、自动音素、纯 V7 文件替换及重开保持 ID 和默认类型，通过；`artifacts/v7-native-roundtrip-05554c8b.json`。该项没有渲染。
- 两次 stdio 合成结束后零会话，前台窗口不变。当前聊天未直接连接 VOCALOID MCP；客户端重连待用户执行。

V7 混缩、全部样式/表现参数的声音效果、复杂扩展迁移、设备与 DAW 尚未逐项运行验证。V6 [功能矩阵](feature-matrix.md) 不自动继承为 V7 证据；本次没有重跑全量套件。