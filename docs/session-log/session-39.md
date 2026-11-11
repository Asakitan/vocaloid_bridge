# Session 39: 整曲制作中的桥接扩展与 AI 声库实测

日期：2026-11-11

## 目标

在一首完整歌曲（`E:/VC/LabyRinth`，IA :[R]，787 个手写音符，5 个分段工程）的调教过程中，按"遇到 MCP 缺功能就直接修"的要求补齐桥接能力，并把实测到的 AI 声库行为写进文档。包版本仍为 0.27.0，未改接口数量。

## 修改（`native/ScoreOperations.cs`，Release 构建 0 警告 0 错误）

- `controller.set`、`pitch.set`、`automation.set` 接受 `points_file`：工作区相对路径的 JSON 点数组，经 `PathGuard.Under(Workspace, …)`、禁止链接、限制大小后读取，其余与内联 `points` 完全一致。起因：一段的 PitchBend 曲线有 400–800 个点，无法内联传递。
- `note.batch_update` 接受 `updates` / `updates_file`：逐音符补丁（`note_index` 加 `number`、`duration_tick`、`velocity`、`ai_expression`、`expression`、`ai_vibrato_enabled` 中的任意项），在一次原生事务内提交。
- `batch.run`：按顺序执行 `operations` 或 `operations_file` 中的既有操作，走与单次调用相同的路径，遇到第一处失败即停并返回 `executed`、`total`、`failed_index`、`error`。不是原子批处理：失败之前的操作保持已应用。
- 共用辅助 `ScoreWorkspaceJson(file, name, maxBytes)`。

## 实测（IA :[R]，逐段渲染后与原唱/自身基线比较）

- **Expression 是"唱法强弱"而不是第二条音量线**：同一句相对 50 的变化（0.4–1.5 kHz / 1.5–4 kHz）——0：−16 / −22 dB；15：−11 / −14 dB；85：+5 / +13 dB；100：+9 / +13 dB。用它逐句做轻声/强声，再用 Dynamics 把随之变化的音量拉回目标。64 句全部按句设置后，各句相对模型预期的误差约 1 dB。
- **Dynamics 近似线性增益**（64 为单位增益，0 静音），但衰减只兑现约 77 % 的分贝值。
- **S5Character** 与 Expression 类似但更偏 4 kHz 以上（+45：4–9 kHz +10 dB；−45：−9 dB）；**S5Air** 增加气声（+70：9 kHz 以上 +9 dB，1.5 kHz 以下 −2～−3 dB）。
- **PitchBend（PitchBendSens 24）是精确的阶跃式移调**（每半音 341.33 单位）；+3～+12 半音、50–190 ms 的跳变配合降低 Dynamics 可以唱出音符模型本身不会产生的假声翻转。pYIN 会把这种翻转读低八度，验证要用谐波梳。
- AI 音符表情：`PitchDriftStart` 0 / 0.5 / 1 为无 / 默认 / 深的起音滑入，但在连音音符上设 0 会让过渡提前约 100 ms，只能用于句首；`AmplitudeWhole` 约 ±6 dB；`PitchTransitionStart` 大于 0.5 只会放慢上行滑音，未采用。
- **"-" 延续音符保持的是前一音节的最后一个音素**：带尾辅音的音节要拆成"头音符（声母+元音，显式音素）＋延续＋只含尾辅音的短音符"，否则长音会哼在辅音上或直接无声。"-" 之前有休止也会无声。
- 辅音最多提前约 200 tick 起音；句末元音在音符约 70 % 处结束。`phoneme_timing.get/set` 的位置是相对音符起点的 tick，且只有渲染过一次之后才存在（重建音符后要先渲染再设）。
- 日语 `N` 对 AI 声库是清音，应使用 `N\\`；拨音比元音低 10–15 dB。英语 `T` 约 115 ms 且近乎无声，可用音素时值缩短。

## 验证

- 五段 r13 渲染：与原唱的逐音符音高 RMS 差中位数 0.37–0.41 半音（未调教基线 0.41–0.52），25 处翻转中决定保留的 23 处全部落在目标音高（1 处读数偏高 1.8 半音，自 r11 起一致），无失声音符。
- 加入逐句 Expression 后（r12、r13）上述音高与翻转读数保持不变。
- `batch.run`、`points_file`、`updates_file` 在五个会话上各执行多次（每次 7 个操作、数百个点），全部返回 `failed_index: null` 并经渲染读回。

## 未完成

- `batch.run` 未做成原子事务；失败后的回滚仍需调用方处理。
- Expression / S5Air / S5Character 的数值只在 IA :[R] 上测过，其他 AI 声库未验证。
- 以上扩展没有新增自动化回归用例，只有本次制作中的真实调用证据（`curves/*_tune.json`、`output/labyrinth_sec*_v07.vpr`、`output/labyrinth_sec*_r13.wav`）。这些歌曲制作中间数据和音频保留在本机，不随公开仓库发布。
