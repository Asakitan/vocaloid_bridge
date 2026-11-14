# Session 48: V7 音频反转与限制调查

日期：2026-11-14。

## 目标

继续处理会话 47 明确列出的限制。保留已安装引擎、私有桌面与原始工程保护，不把未实现的原生功能标为通过。

## 实现

- V7 安装的 `WaveOfflineRenderer.dll` 未导出 V6 的反转及 VOCALO CHANGER 创建、销毁与渲染入口。安装版 Yamaha `WaveFile` 仅支持 44.1 kHz、16 位 PCM 单/双声道，最初的受限原型已被下述实现取代。
- V7 `process_audio` 的 `reverse` 对 PCM/IEEE 浮点 RIFF WAV 使用桥接有界缓冲区逐帧倒序，产生独立 WAV，源文件不变。结果返回 `backend=bridge.pcm_frame_reverse`、`native=false` 和时间元数据提示；不是 WOR 原生渲染或替代合成器。
- 多数据块须各自包含完整帧，输出按全部音频帧反序并合并成单个数据块，以便常见 WAV 解码器读取；有效标准整数 `smpl` 循环端点随帧重映射。单数据块、无 `smpl`/`plst` 且位置字段一致的 cue 点也重映射，允许含有效 `labl`/`note`/`ltxt` 的 `LIST/adtl`；唯一且范围有效的区域按长度反向映射，冲突长度、重复 ID、零长度、越界或异常列表保持相关 cue 原样。普通、标签及区域 cue 均跨块检查重复 ID；cue ID 和区域引用各最多扫描 65536 个，超限保留所有 cue 原样。分数、无效、未知类型或带厂商扩展的循环，以及其他时标保持原样。回执分别报告已反转与未修改的循环、cue 点及未修改块。压缩或未知扩展编码、不完整帧和非 RIFF 输入明确拒绝。V6 仍使用原生 WOR 反转。
- `vocaloid_features` 提供反转操作模板；`vocaloid_operations` 和工具说明区分 V7 支持格式、实际实现与仍不支持的变声。
- 已为空的 `dvqm_clear` 不再开启事务、标脏或失效子引用；归档和冻结守卫只对确认已空的目标放行，非空 AI 编辑继续拒绝。
- AI 音符增加显式 `storage="bridge_metadata"`：Attack/Release 注记绑定音符身份并参与既有归档历史，保存于 `vocaloid_bridge_ai_dvqm_v1` 未知字段。回执 `native=false`、`applicable_to_current_part=false`；不修改原生 DVQM，也不改变 AI 合成。默认原生路径和反射保护不变。
- 原生打开和文件级 VPR 输出检查 AI 音符的 `singingSkill` 与非空 `dvqm.attack`/`dvqm.release` 冲突；分别在原生加载和创建目标前拒绝。`score_patch` 仅对指定冲突音符允许显式移除整个 `dvqm` 或 `singingSkill` 子树并另存；其他扩展音符结构守卫保持。
- V7 `IsChannelMute` 是受独奏影响的有效通道状态，不是持久化的静音标记。使用安装版仍提供的 `VIS_VSM_WIVSMTrack_mute` 原生导出读取独立标记；轨道摘要的 `mute` 表示该标记，`channel_mute` 报告有效状态。修改静音时暂时解除并恢复会话内已独奏的轨道；两种标记可同时保存。功能与操作发现区分两种状态，V6 保持原有行为。
- V7 `track.update` 新增 `solo_state` 的 `Off`、`On`、`Defeat` 原生状态及功能模板；与布尔 `solo` 互斥，布尔 `false` 选择 Off。三态切换保留未请求改变的静音标记；V6 对此参数明确拒绝。
- V7 扩展轨道身份签名和原生读回核对纳入 `soloState`。V6/V7 的带实体扩展工程在轨道身份字段修改前，先在独立克隆上执行并检查归档输出；会制造真实身份冲突的请求不改变原会话。
- 双产品复合轨道更新先核对名称 setter，再进行后续状态操作；失败时恢复不进入原生撤销历史的静音、独奏及录制状态，恢复本身失败会标脏并同时报告。
- 双产品乐谱入口的轨道类型、表现模式、音色、旁路和控制器类型，以及 V7 独奏状态，只接受各自的原生枚举名称，不把数字字符串当成枚举值；原有大小写规则保留。歌词和轨道故障探针使用所选产品的当前宿主及核心程序集。
- 带扩展字段的工程允许进入既有会话自有冻结/解除流程；保存与克隆仍先应用归档保留并恢复作者态，冻结期间实际修改仍受守卫保护。新增冻结与 AI DVQM 注记发现模板，V6/V7 功能导航分别为 39/41 项。

## 验证

- V6/V7 各 35 个原生源文件、218 个引用的语义预检均为 0 错误；两产品 Release 构建成功。
- V7 真实 stdio 的原生合成人声、8/16/24 位 PCM、标准与扩展浮点、48/96 kHz、三声道、跨缓冲区、多数据块逐帧/逐字节对照、标准整数 `smpl` 循环及标签/区域 cue 点重映射、分数/厂商扩展与歧义区域保留通过；多数据块输出经独立解码器读回，不完整帧与未知扩展编码拒绝，源文件不变；普通/标签/跨块重复 cue ID 与 65537 个 ID 超限保护通过：`artifacts/feature-acceptance-0cb552311264/summary.json`。普通重复 ID 被改写的失败基线为 `artifacts/feature-acceptance-304d7632f8a7/summary.json`；区域未映射基线为 `artifacts/feature-acceptance-9b0abd720b76/summary.json`，普通标签误拒绝基线为 `artifacts/feature-acceptance-29026a8119ae/summary.json`，独立 cue 修复前失败为 `artifacts/feature-acceptance-a94e8af30e1f/summary.json`，标准循环端点修复前失败为 `artifacts/feature-acceptance-b6b056a70c60/summary.json`；先前仅对多数据块逐字节比较的版本不能被该解码器打开，失败基线为 `artifacts/feature-acceptance-c6c9c5964de4/summary.json`；更早的受限原型回执 `artifacts/feature-acceptance-c520e476562b/summary.json` 只代表当时实现。
- V6 原生 WOR 反转、归一化和功能发现通过：`artifacts/feature-acceptance-d321081a9acd/summary.json`。
- V7 乐谱分类首次验收 15 项及清理通过、两项失败：`artifacts/feature-acceptance-28b110cac043/summary.json`。旧首音符夹具补充 V7 轨道声库作用域后通过：`artifacts/feature-acceptance-f5c1f1d24b4d/summary.json`。先前依据有效通道状态误判静音与独奏互斥，临时拒绝路径已撤销；`artifacts/feature-acceptance-3f22e704e08c/summary.json` 确认原生独立标记与保存字段一致，旧实现遇到其他轨道独奏时修改静音失败为 `artifacts/feature-acceptance-05faf789184e/summary.json`。最终 V7 AI/音频轨、多独奏恢复、双开保存重开、组合关闭、Solo Defeat 保留与发现通过：`artifacts/feature-acceptance-52fe2fd574d6/summary.json`；受测单独静音和独奏未增加原生撤销项。V6 两项回归及清理通过：`artifacts/feature-acceptance-a1e38b533eeb/summary.json`。
- V7 双轨原生混缩的独奏加自身静音、退出独奏后其他轨道静音与第一条分轨 PCM 对照通过：`artifacts/feature-acceptance-b8e102bb94a3/summary.json`；不代表全部工程或设备组合。
- V7 `solo_state` 三态发现、切换、静音保留、保存重开、参数拒绝和 `Defeat` 参与双轨原生混缩通过：`artifacts/feature-acceptance-1fb9dfec16f3/summary.json`；初版切换到 Defeat 会清除静音的失败回执 `artifacts/feature-acceptance-45d0b2446bd5/summary.json`。V6 新参数拒绝及既有操作回归通过：`artifacts/feature-acceptance-f947acdb74c1/summary.json`。
- 修复后 V7 乐谱分类 17 项及清理通过：`artifacts/feature-acceptance-32da71dc4129/summary.json`；扩展工程身份、未知字段及清理通过：`artifacts/feature-acceptance-5bebf6ac713e/summary.json`。
- V7 同形、不同 `soloState` 的扩展轨道打开/重排/重开，以及真实身份碰撞前置拒绝通过：`artifacts/feature-acceptance-ae04d8be8cbc/summary.json`；先前身份误拒绝为 `24e5864304ae`，修改成功后才产生碰撞的失败基线为 `ffa5559762c2`。V6 静音状态碰撞前置拒绝通过：`artifacts/feature-acceptance-9922cd58c241/summary.json`；双产品合法扩展编辑分别通过 `44a6952d9af5`、`ec79f1de0dc3`。
- V7 工程生命周期和原生合成 7 项及清理通过：`artifacts/feature-acceptance-8344e012cb7b/summary.json`。
- V7 原生拒绝超长名称后仍留下静音/Defeat 的失败回执为 `artifacts/feature-acceptance-d77f304a2cef/summary.json`。修复后含录制开关的超长名称复合更新未留下状态或历史变化：V7 `artifacts/feature-acceptance-c47a027d0f83/summary.json`、V6 `artifacts/feature-acceptance-69e7bdec4560/summary.json`；本例实际验证录制开关恢复，以及名称被拒绝时静音/独奏未进入后续操作。
- 修正歌词故障探针使用旧宿主的问题后，在双产品当前私有宿主中观察歌词已暂存，再注入提交前异常并核对原状态；轨道探针先确认静音、独奏和录制均关闭，再改变三项并注入异常，验证轨道、音符、脏状态及历史恢复。V7 `artifacts/feature-acceptance-97caf450ad44/summary.json`，V6 `artifacts/feature-acceptance-3b3f08ae53a3/summary.json`。
- V7 乐谱分类在枚举名称收紧前的最终轨道状态改动后 17 项及清理通过：`artifacts/feature-acceptance-af3cbb665192/summary.json`；双产品枚举收紧后的轨道、表现和控制器名称正负例及清理通过：V7 `artifacts/feature-acceptance-b229734e56f5/summary.json`，V6 `artifacts/feature-acceptance-c67b15fd5ad1/summary.json`。修前 `solo_state="2"` 被接受为 `artifacts/feature-acceptance-8b6d72a35eb3/summary.json`；`track.create` 的 `type="2"` 和 `robot_mode="0"` 被接受为 `artifacts/feature-acceptance-68b1d3c0bc40/summary.json`。此修复后双产品语义预检和专属 Release 构建通过。
- V7 主效果、轨道效果和预设三项及清理通过：`artifacts/feature-acceptance-53e100b0dd26/summary.json`；歌词、音素、语言、目录与样式七项及清理通过：`artifacts/feature-acceptance-ce519fbbc37e/summary.json`。
- 修复前的 V7 反转拒绝基线：`artifacts/feature-acceptance-5c92c4b90d57/summary.json`。
- V7/V6 扩展工程空清除、保存、引用、历史与非空冲突保护分别通过：`artifacts/feature-acceptance-ce0ac0631c41/summary.json`、`artifacts/feature-acceptance-a0cc24253bbe/summary.json`。冻结轨道的缓存和历史不变、实际编辑仍拒绝分别通过：`artifacts/feature-acceptance-7c13162b245b/summary.json`、`artifacts/feature-acceptance-6570641b3c18/summary.json`。修前归档误拒绝为 `artifacts/feature-acceptance-148f16106563/summary.json`，冻结误拒绝为 `artifacts/feature-acceptance-6ab3c64f1964/summary.json`。
- AI 桥接注记的 Attack/Release 读写、功能发现、原生权重不变与独立编辑、撤销/重做、音符删除/复制/拆合、克隆、保存/重开、冻结拒绝、重复写入和未知字段保护通过；受测工程写入注记前后原生人声逐样本一致：V7 `artifacts/feature-acceptance-edbda98e1c1e/summary.json`，V6 `artifacts/feature-acceptance-fbcfee057c8b/summary.json`。原生 DVQM 反射保护分别通过 V7 `artifacts/feature-acceptance-0ec92e14681a/summary.json`、V6 `artifacts/feature-acceptance-72ae95f65fda/summary.json`。结构验收脚本先因重复传参和重复执行产生失败回执 `5ae96a85ab8d`、`48596be95fc9`，修正后通过；旧实现忽略存储选择并错误报告原生的基线为 `artifacts/feature-acceptance-b3d2ec7aba72/summary.json`。
- 隔离 V7 工程同时写入两种表示后原生重开读到 Attack，但 Singing Skill 权重变零、保存结果丢失该子树：`artifacts/feature-acceptance-1a05f4587bb9/summary.json`；V6 同样将 64/64 权重读为 0/0：`artifacts/feature-acceptance-02e8a3a519a1/summary.json`。保护后，冲突工程在打开前拒绝，文件输出不发布；显式另存保留 Singing Skill 或 Release 的两条路径均通过，其他 JSON、资源及原文件保留：V7 `artifacts/feature-acceptance-b48c40ba8f6a/summary.json`，V6 `artifacts/feature-acceptance-8936678672bb/summary.json`。扩展工程最初因音符守卫误拒绝显式移除，失败基线 `artifacts/feature-acceptance-738be8faa1e3/summary.json`；未证明原生双表示可共存。
- 默认 V7 模板冻结先因扩展工程保护被拒绝：`artifacts/feature-acceptance-44cf2a8ca549/summary.json`；放行后冻结、保存、克隆、解除及重开通过：`artifacts/feature-acceptance-60c3b4b23743/summary.json`。带 root/track/part/note、音高、控制器、自动化、效果/参数未知字段及额外资源的工程，V7 `artifacts/feature-acceptance-382ecd42cead/summary.json`、V6 `artifacts/feature-acceptance-bc5654ce2c9d/summary.json` 通过模板绑定、保存/克隆/重开及解除后撤销/重做；冻结缓存补偿预送后与冻结前混音按 2/32768 容差对照通过，已有 Attack 的清除仍被拒绝。未验证所有扩展组合或实时播放路径。

## 仍待处理

V7 反转不支持压缩或非 RIFF WAV，分数循环、厂商扩展、播放列表关联或歧义 cue 及其他时标未随帧倒序重映射；V7 原生 VOCALO CHANGER、VMM 素材及片段音频效果未发现可用接口。AI DVQM 的原生表示和撤销冲突仍受保护。没有运行全量套件；独立 stdio 验证不等于当前聊天已重连，已运行客户端需先保存关闭工程再重连。