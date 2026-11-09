# 会话 07：后台原生完整性与实际声音验收

日期：2026-11-10。版本：0.2.1。目标继续进行，不将本轮增量称为全部功能验收完成。

## 约束与分工

保持创建、打开、编辑、保存；仅在私有 Windows desktop 使用已安装原生引擎。用户选择暂不安装经典声库试用，继续代码与公开样本。三个子 agent 均使用 gpt-6.1-terra：经典格式与样本、Robot/参数、音频路由与 VoiceColor；主线负责集成、完整性检查、Breath、文档及发布。

## 代码变更

- `native/EngineSession.cs`：VSM 缓存容量设零并验证，保留每宿主独立命名空间；渲染等待有效波形及完成状态，返回 `render_observation`；内部非 44100 Hz 声乐合成快速报错；修正 `OpenSequence` 的 schema 目录。
- `native/ProjectIntegrity.cs`：经典 VPR 缺声库预检，载入后检查类型/数量/身份，保存与克隆在发布前检查原生快照。已有输出和源文件保护保持。
- `native/ScoreOperations.cs`：新增 `note.expression_bounds`；VoiceColor 描述包含 `applies_to` 和 `applicable_to_current_part`，区分原生可存储字段与当前引擎适用字段。
- 36 工具、109 结构化操作；操作目录已由源码与文档再生成。
- 新增或扩充会话、Robot、路由、VoiceColor、Take、公开 PPSF 样本获取与格式完整性测试；整合入口纳入维护中的 VoiceColor 和完整性用例。

## 原因与证据

### Robot

相同 Hard VPR 在全新宿主可变声，而先渲染再编辑的同会话输出曾保持旧 PCM。持久 Lua 控制器和单纯等待完成均未解决；两项实验保留失败记录。将 `CacheCapacity` 设为零后，原失败用例 `feature-acceptance-b08ff3a55109` 通过，同宿主双会话 `robot-concurrent-55f6b5ff5c73.json` 保持另一会话音频。未恢复共享缓存名，未调用全局 ClearCache。

### 经典格式

静态 VSM 数据库计数分支与当前 Dse=0、Dnn=21 时强制选择 AI 模式的实测一致；版本专属指令见 `classic-native-audit-025cb925c173.json`。原生保存还会省略缺失经典声库的身份。新增检查在加载或发布前报出明确错误，而非保存破损身份；这不是经典合成修复或完整经典往返。

`feature-acceptance-8a94a4ae3dcd` 验证打开、克隆、覆盖保存保护和正常 AI 往返。后续 `feature-acceptance-2ccd799e0d5e` 使负例由当前原生创建，不再依赖历史 VPR，并验证当前操作目录。保护测试逐字节检查原件和已有目标，核对源会话轨道、音符与声库。原生 Save 内部修改标志不在无副作用承诺内。

### 公开 PPSF3

作者公开的 `Monologue.ppsf` 自报 PPSF3.2；原件和来源存于被忽略的 `.runtime`，没有把歌曲加入 Git。`tools/fetch_public_ppsf_fixture.py --source monologue` 下载原始 ZIP 并记录来源；`--source utaformatix` 保留固定版本的开源最小格式夹具，两者不混淆。

`feature-acceptance-a3cc87f45ce7` 验证 190 个源事件的绝对位置、时值、音高、歌词，80 BPM 和 4/4，以及原生保存重开后的音符、音素、速度与拍号。NT 符号有 99/190 与导入后的 VOCALOID 音素不同；两套声库身份不等价，不宣称 NT 音素或声库无损迁移。

显式调用 `voice.set` 选择本机 asa 后，声库 ID 保存重开保持，原生输出 4,387,954 帧、99.5001 秒 WAV，独立流式解码 RMS 0.03772。`feature-acceptance-9ec33f2e51bf` 的原 case 因通用 WAV 读取器 30 秒上限失败；`ppsf3-render-stream-check-9ec33f2e51bf.json` 只复核已有 WAV，没有重渲或改写原失败。局部检查器现支持最长 600 秒的块解码，修正后的整条 case 未重跑。

### 参数与实际声音

- 19 个表现字段与全部 VoiceColor 存储：`feature-acceptance-9eec19449679`；新适用性字段及素材往返：`feature-acceptance-bf40360385c5`。
- 三个 AI VoiceColor 参数和旁路：`feature-acceptance-dc7fdcb678e4/voicecolor.audio.json`。其六个经典字段在 AI 声音中未测得变化，当前返回适用性。旧运行器误选全量覆盖造成非零退出，已修默认分类选择，不重渲未变声音。
- Take：`score-parameters-66761d50d26c.json` 独立创建夹具，lane 0/9 声音差异、参数和旁路保存重开通过。公开包装器仅有 Lane 这个专属值。
- Breath：`feature-acceptance-f01a08f3680e` 验证启用、频率与呼气量的声音差异，以及保存重开；Male/Female 在此 AI 样本 PCM 相同，未宣称类型听感差异。
- 内部采样率与输出率分离：`audio-routing-acda7649870c.json` 六种非零输出组合；`audio-routing-guard-9f833b494596.json` 48/96 kHz 参数读回和快速报错。实际 48 kHz DSE 失败，96 kHz DSE 未直接运行。离线输出总线求和不等于 DAW 路由。

## 验证边界与后续

Release 构建为 0 警告、0 错误；`feature-acceptance-983dee33baea` 的生命周期、真实 PPSF3、双 AI 声库、特殊音素及清理 6 项通过。只跑相关定向检查，没有把旧 76/5/2 整合回执改成全部通过。

经典声库、经典 Emotion/Singing Skill/VoiceColor 的实际声音及完整身份往返，设备和 DAW 仍是环境依赖。当前聊天的既有 MCP 进程保留旧工具发现；新 stdio 已验证 36 工具，客户端重载后使用新版本。没有接管用户编辑器、安装声库或改变授权。
