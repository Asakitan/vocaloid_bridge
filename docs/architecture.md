# 架构

```mermaid
flowchart LR
    Client[MCP 客户端] -->|stdio| Python[Python MCP 服务]
    Python -->|UTF-8 JSON 行协议| Native[私有 desktop 中的 STA 宿主]
    Native --> Wrapper[已安装的 VOCALOID6 .NET 封装]
    Wrapper --> Engine[VSM / VDM / DSE 原生组件]
    Wrapper --> Audio[WOR / VEM / VAE 原生音频]
    Wrapper --> Library[G2PA / VSStyle / VMM 原生素材]
    Native --> MIDI[明确选择的 WinMM 输入或显式事件流]
    MIDI --> Engine
    Python --> Score[VPR / MIDI 数据编排]
    Engine --> Output[工作区 output]
    Audio --> Output
    Library --> Private[私有素材与剪贴板资源]
    Score --> Output
```

## 进程边界

客户端通过各自的用户级配置启动同一 Python 入口。VS Code Stable/Insiders 使用 `servers`，Claude Code/Desktop 使用 `mcpServers`，Codex 使用 `mcp_servers`。绝对路径及显式 `PYTHONPATH`、`VOCALOID_WORKSPACE` 使启动不依赖客户端当前目录。不同客户端持有独立 MCP 进程；生成文件仍统一限定在本项目的 output。当前工作区配置保留。

Python 使用 Win32 `CreateDesktopW` 创建私有 desktop，以 `STARTUPINFO.lpDesktop` 启动原生宿主。宿主不实例化 WPF Application 或 MainWindow，也不运行 VOCALOID6 的图形启动入口。不存在切换到用户桌面的分支。

启动前创建匿名管道与 Job Object；宿主先以挂起状态创建，加入 kill-on-close Job 后继续执行。任何隔离或进程归属设置失败都会终止启动，不换用普通桌面。

Windows CLR 会锁定正在运行的 DLL；宿主从 `.runtime/hosts` 下本次会话独有的完整构建副本启动，关闭后删除副本。构建输出不再被活动宿主直接加载，此机制不改变后端或程序集内容。

VSM 管理器使用每宿主唯一的 `VocaloidBridge-<GUID>` 缓存命名空间，而 VDM/DSE 继续读取原安装数据。固定使用编辑器的 `VOCALOID6` 命名空间会使一个管理器退出时删除其他宿主的 WAV 缓存；双宿主回归已复现该问题，因此缓存隔离与 desktop 隔离同时执行。`vocaloid_status.cache_namespace` 返回实际命名空间。

管理器的 `CacheCapacity` 设为零并读回确认，状态返回 `render_cache_bytes=0`。这一独立设置修复已渲染片段切换 Robot 后复用旧声音的问题；没有清空其他会话缓存，也没有改回共享命名空间。同宿主双会话的音频保留有定向验证。

## 原生状态

每个会话持有真实 `WIVSMSequence`。对象引用限定于所属会话；删除性操作使子引用失效，关闭会话清理所有引用。所有原生方法在宿主同一 STA 线程顺序执行。

新建、打开、保存和关闭直接使用 VSM 方法。保存由引擎写出工程目录，再封装 VPR；原始输入和临时文件分离。乐谱编排使用 VPR 结构化数据，原生打开是独立且必要的验证步骤。

原生写入器会省略未知 JSON 字段与额外 ZIP 成员。`ProjectArchivePreservation.cs` 从安装版 schema 识别字段，将受支持的未知字段绑定到原生 track/part/note 对象身份并监听生命周期；真实提交、撤销、重做、回滚同步实体、root/master、速度/拍号/控制器事件和资源映射快照。速度与拍号扩展按明确的原生操作映射，不依赖旧数组索引；受测速度地图合并按 tick 建立映射，拍号合并在独立候选中逐事件复现原生小节换算。控制器扩展当前支持受测的直接编辑与历史，复制和跨工程迁移另有保护。复制及拆合时子对象按唯一语义签名关联并迁移扩展，冲突时回滚；保存只向全新的原生 JSON 叠加未知叶子，已知字段仍由当前引擎写出。扩展剪贴板粘贴和工程合并先在独立候选中执行并验证原生保存；剪贴板轨道、片段或音符选择均携带整份工程级不透明资源，音频轨及片段的原始/处理 WAV 迁移已有受测样本，并检查实际 ZIP 的条目与解压大小限制。剪切不按实体归属删除工程级资源，异常时保留快照；其他复杂数组和音频组合仍有保护边界。扩展工程的原生合成、MIDI 导出和离线混缩使用独立原生快照并返回源会话 ID。候选预检增加工程复制和原生保存开销，资源私有副本保留至会话关闭。

打开时以已安装程序集目录作为原生 `vsqxSchemaDirPath`。`ProjectIntegrity.cs` 在载入前检查已知的经典声库缺失条件，在载入后核对轨道类型、数量、片段数与输入的显式声库身份；保存和克隆则先核对原生输出与当前会话的非空主/副声库及根 voices 表，再发布或打开副本。失败不替换已有目标，不用桥接元数据伪装原生声库。原生 Save 自身可能更新内部修改标志，检查不承诺整个引擎内部完全无副作用。

结构化编辑使用原生事务，提交后重新取得对象并核对修改。直接音高通过音符的 `SetDirectPitch` 写入，不依赖交互式绘线状态。原生格式交换负责导入、MIDI 导出、复制、恢复和合并；导入资源保留到目标会话关闭。私有剪贴板持有独立原生快照，不读写系统剪贴板，源工程关闭后仍能粘贴。

`vocaloid_operations` 从随包发布的结构化目录提供全部操作名称、所属工具与文档契约；目录由原生 dispatch 和相关 Markdown 生成，使用 `tools/generate_operation_catalog.py --check` 检查漂移。目录仅代表调用面，实测状态仍由功能矩阵记录。

## 人声合成

合成前始终调用原生 `Commit(false)`。该调用除了提交编辑，还负责刷新渲染队列；即便序列没有暂存编辑也不能跳过。无暂存编辑且原生错误为 `NoError` 时，Commit 返回 false 不代表失败。

启用 Robot Voice 时，宿主使用安装的 Lua 管理器和原生效果对象恢复相应脚本路径与渲染时序。路径属于运行时状态，不保存在 VPR；片段合成和整曲混缩均在提交渲染队列前恢复，不初始化编辑器 App。

传统片段的 Singing Skill 同样按已安装目录解析 plugin ID，并在渲染前恢复原生脚本与时序；请求不接受任意脚本路径。音符级 HMM 权重另有独立入口，不与 Singing Skill MIDI 效果混为一谈。

宿主设置 Lua 控制器和渲染观察者，启动原生异步渲染，并在同一 STA 线程轮询原生观察者。只有目标片段具有有效波形，且收到其完成事件或序列完成状态后，才检查 RIFF/WAVE 并发布到 output。返回 `render_observation` 记录开始、完成和进度；Python 再检查实际音频帧、峰值和 RMS。原生等待上限为 120 秒，外层 RPC 为 180 秒，不通过声卡播放或 UI 渲染。内部声乐合成限定 44100 Hz；混缩输出采样率独立设置。

## 音频与素材

离线反转、规范化、拉伸、移调和变声使用 WOR。VAE 以明确的 VST 主机连接方式初始化，再进入 Manual 模式，通过文件片段和 VEM 完成整工程/整轨混缩；不启动播放或选择物理设备。分轨保留轨道/片段效果并旁路主效果和主音量自动化。自定义秒区间和尾长参数明确拒绝。

独立的传输分支使用用户明确选择的设备 ID 和 VAE StandAlone 模式，不改系统默认设备或用户编辑器。一个宿主最多持有一个准备好的传输；释放前保护对应会话，关闭先释放设备和回调。`SetCurrentTime` 的异步应用与已观测位置分开返回，静音设备测试验证了时钟推进、停止、定位及释放。

`MidiRecordingOperations.cs` 通过 System32 的 WinMM 接口枚举输入，只有明确给出设备 ID 与名称才打开；另有调用者显式提交的事件流模式。设备回调仅入队或记录错误，所有 VSM 访问仍由宿主 STA 线程完成；无效输入、回调故障或队列溢出时停止提交。停止时按工程速度映射转换并在事务中写入。可选的本会话 transport 同步在停止时先释放设备传输再提交。录制期间保护工程、库和剪贴板写入；关闭或退出先释放输入。事件流、静音同步、回调逻辑及自有虚拟输入的 WinMM 回调已验，物理硬件输入和实际驱动错误通知未验，详见 [MIDI 录制](midi-recording.md)。

编辑器官方不具备波形录音功能，录制 WAV 后由现有音频导入入口接收。安装的 VST3 插件已有固定管道名路径的静态证据，私有 desktop 本身不证明跨进程 IPC 隔离；尚未加载插件或验证 DAW 同步，详见 [音频录制与宿主边界](audio-recording.md)及 [DAW IPC 调查](daw-ipc.md)。

`TrackFreezeOperations.cs` 先生成原生轨道混音，再按首片段起点减预送时间物化自有 WAV。冻结放置范围覆盖全部片段；回放不重复套用已烘焙的轨道音量/声像。冻结前保存真实效果旁路值，序列化时恢复到作者状态；原生冻结标志不持久化。解除冻结的原生调用会删除 WAV，因此入口只接受该会话登记的私有路径。

G2PA、样式和 VMM 素材服务按需初始化，并在宿主退出时释放。自有媒体位于 `.runtime/library`；修改和删除只允许该私有目录。VMM 的属性保存在 `property.json`，音符资源保持独立。原生 Attack/Release 通过已安装数据库的组件 ID 和级别名称映射。

原生 VSStyle 捕获、覆盖、属性编辑和删除仅操作 `.runtime/library/styles` 中的自有样式；系统样式和原有用户样式只读。捕获直接复制原生 MIDI／音频效果参数，不创建替代音源。

音频素材捕获依据原生区域和工程速度映射，在私有 `audio-sources` 中物化选定的 WAV 采样；原件保持不变。此路径保留采样格式与数据，不承诺保留 WAV 的所有附加元数据块。

VMM 的原生素材写入器保存次声库字段，但当前读取器返回空值。桥接层对原生 `.vsclip` 使用 JSON 解析补充该字段、标注数据来源并检查非空冲突；人声合成仍只使用安装的原生引擎。

原生 VMM 不持久化无效音素标志或 AI Attack/Release；新建自有 `.vsclip` 将它们放在 `vocaloid_bridge_phoneme_validity_v1` 扩展中，导入时核对音符身份与已安装数据库。原生 VPR 也不持久化无效音素标志，桥接层以 `vocaloid_bridge/phoneme-validity-v1.json` 保存，打开和复制时恢复。文件级 VPR 编辑保留该条目，但会拒绝使引用音符不匹配的修改；这些扩展不声称被其他软件保留。

公开 PPSF V2 与 VSQX3/4 样本的原生导入保留了音符数据，但当前缺经典 DSE 声库时，保存会丢失经典身份，载入也有强制 AI 分支。该分支已定位到安装版本的 VSM 数据库计数路径；保护检查对此明确报错，经典合成与无损往返保留为环境依赖。用户选择仅使用 AI 声库，不安装经典试用。作者公开 PPSF3.2 则已完成 190 音符的原生导入、保存与重开；NT 声库不等同本机 VOCALOID 声库。

验收客户端记录前台窗口及所属 PID，区分用户正常切换和测试进程抢焦点，不恢复或激活窗口。上轮整合为 76 通过、5 失败、2 个缺样本项；本轮定向修复与复查分开保留回执。`project_render_part` 返回原生 `lua_result`，`NoError` 本身不构成效果证据；Robot、Take、Breath 与三个 AI VoiceColor 参数已另有实际 PCM 差异。VoiceColor 的当前轨道适用性另行返回，存储非适用字段不代表合成器使用了它。覆盖范围以功能矩阵逐项状态为准。

## 边界

MCP 不暴露任意进程调用、内存地址、脚本执行、授权数据或图形窗口命令。原生错误原样转换为协议错误，不使用静音文件、旧音频、其他音源或 UI 操作掩盖失败。
