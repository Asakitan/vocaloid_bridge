# 参考实现对照

2026-11-09 阅读了用户指定的 [soyoshio/AI-VOCALOID-MCP](https://github.com/soyoshio/AI-VOCALOID-MCP/tree/main)。页面显示的提交为 `1b2980c33d69fa1c4477cf54a0c9136028728aed`。本工程没有直接复制或引入其源码。

## 可参考内容

- `server.py` 把工程、轨道、音符和导出组织为易于模型调用的工具。
- `vpr_sdk/models.py` 区分 V5 与 V6 字段，保留未知音符字段、手绘音高与控制曲线。
- `vpr_sdk/io.py` 在导出时保留原工程的内嵌音频。
- `voice` 与 `aiVoice` 表示不同的音色层级，不能把其中一个 ID 当作另一个使用。
- 音名换算使用 C4=60，时间分辨率为每四分音符 480 tick。

## 当前工程的对应实现

| 参考能力 | 当前实现 |
| --- | --- |
| 工程和音符 JSON 编排 | `projects.py` 保留原始 JSON 的未知字段与 ZIP 条目 |
| 音高和时间单位 | `music.py` 使用 480 PPQ 与 C4=60，验证单声部重叠 |
| 已知歌手表 | 不照搬预置表，由本机 VDM 查询实际声库 |
| 文件层新建/导出 | 同时提供文件编排及原生 VSM 创建、保存、关闭 |
| 实际 VOCALOID 合成 | 参考项目未实现；当前工程单独对接原生引擎，验收见 STATUS |

参考项目的 `export_project` 写出 VPR，不等同于合成 WAV，也不控制编辑器的工程生命周期。这里继续使用独立 desktop 内的原生宿主，不将文件层功能作为合成失败时的回退。