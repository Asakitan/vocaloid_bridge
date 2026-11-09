# 架构

```mermaid
flowchart LR
    Client[MCP 客户端] -->|stdio| Python[Python MCP 服务]
    Python -->|UTF-8 JSON 行协议| Native[私有 desktop 中的 STA 宿主]
    Native --> Wrapper[已安装的 VOCALOID6 .NET 封装]
    Wrapper --> Engine[VSM / VDM / DSE 原生组件]
    Wrapper --> Audio[WOR / VEM / VAE 原生音频]
    Wrapper --> Library[G2PA / VSStyle / VMM 原生素材]
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

## 原生状态

每个会话持有真实 `WIVSMSequence`。对象引用限定于所属会话；删除性操作使子引用失效，关闭会话清理所有引用。所有原生方法在宿主同一 STA 线程顺序执行。

新建、打开、保存和关闭直接使用 VSM 方法。保存由引擎写出工程目录，再封装 VPR；原始输入和临时文件分离。乐谱编排使用 VPR 结构化数据，原生打开是独立且必要的验证步骤。

结构化编辑使用原生事务，提交后重新取得对象并核对修改。直接音高通过音符的 `SetDirectPitch` 写入，不依赖交互式绘线状态。原生格式交换负责导入、MIDI 导出、复制、恢复和合并；导入资源保留到目标会话关闭。私有剪贴板持有独立原生快照，不读写系统剪贴板，源工程关闭后仍能粘贴。

`vocaloid_operations` 从随包发布的结构化目录提供全部操作名称、所属工具与文档契约；目录由原生 dispatch 和相关 Markdown 生成，使用 `tools/generate_operation_catalog.py --check` 检查漂移。目录仅代表调用面，实测状态仍由功能矩阵记录。

## 人声合成

合成前始终调用原生 `Commit(false)`。该调用除了提交编辑，还负责刷新渲染队列；即便序列没有暂存编辑也不能跳过。无暂存编辑且原生错误为 `NoError` 时，Commit 返回 false 不代表失败。

启用 Robot Voice 时，宿主使用安装的 Lua 管理器和原生效果对象恢复相应脚本路径与渲染时序。路径属于运行时状态，不保存在 VPR；片段合成和整曲混缩均在提交渲染队列前恢复，不初始化编辑器 App。

传统片段的 Singing Skill 同样按已安装目录解析 plugin ID，并在渲染前恢复原生脚本与时序；请求不接受任意脚本路径。音符级 HMM 权重另有独立入口，不与 Singing Skill MIDI 效果混为一谈。

宿主设置 Lua 控制器和渲染观察者，启动原生异步渲染，并在同一 STA 线程轮询原生观察者。取得目标片段有效的 `WaveFilePath` 后检查 RIFF/WAVE 格式，将文件发布到 output；Python 再检查实际音频帧、峰值和 RMS。原生等待上限为 120 秒，外层 RPC 为 180 秒，不通过声卡播放或 UI 渲染。

## 音频与素材

离线反转、规范化、拉伸、移调和变声使用 WOR。VAE 以明确的 VST 主机连接方式初始化，再进入 Manual 模式，通过文件片段和 VEM 完成整工程/整轨混缩；不启动播放或选择物理设备。分轨保留轨道/片段效果并旁路主效果和主音量自动化。自定义秒区间和尾长参数明确拒绝。

G2PA、样式和 VMM 素材服务按需初始化，并在宿主退出时释放。自有媒体位于 `.runtime/library`；修改和删除只允许该私有目录。VMM 的属性保存在 `property.json`，音符资源保持独立。原生 Attack/Release 通过已安装数据库的组件 ID 和级别名称映射。

原生 VSStyle 捕获、覆盖、属性编辑和删除仅操作 `.runtime/library/styles` 中的自有样式；系统样式和原有用户样式只读。捕获直接复制原生 MIDI／音频效果参数，不创建替代音源。

音频素材捕获依据原生区域和工程速度映射，在私有 `audio-sources` 中物化选定的 WAV 采样；原件保持不变。此路径保留采样格式与数据，不承诺保留 WAV 的所有附加元数据块。

VMM 的原生素材写入器保存次声库字段，但当前读取器返回空值。桥接层对原生 `.vsclip` 使用 JSON 解析补充该字段、标注数据来源并检查非空冲突；人声合成仍只使用安装的原生引擎。

原生 VMM 不持久化无效音素标志或 AI Attack/Release；新建自有 `.vsclip` 将它们放在 `vocaloid_bridge_phoneme_validity_v1` 扩展中，导入时核对音符身份与已安装数据库。原生 VPR 也不持久化无效音素标志，桥接层以 `vocaloid_bridge/phoneme-validity-v1.json` 保存，打开和复制时恢复。文件级 VPR 编辑保留该条目，但会拒绝使引用音符不匹配的修改；这些扩展不声称被其他软件保留。

公开 PPSF V2 与 VSQX3/4 样本的原生导入保留了音符数据，但保存重开后经典声库 ID 丢失，PPSF 经典轨还变为 AI 轨。新建空经典轨同样出现重开类型改变，尚未找到完整原生修复路径。

验收客户端记录前台窗口及所属 PID，区分用户正常切换和测试进程抢焦点，不恢复或激活窗口。本轮整合为 76 通过、5 失败、2 个缺样本项；定向修复与复查分开保留回执。`project_render_part` 还返回原生 `lua_result`；`NoError` 不构成效果已生效的证据，Robot 目前的声音差异仍失败。覆盖范围以功能矩阵逐项状态为准。

## 边界

MCP 不暴露任意进程调用、内存地址、脚本执行、授权数据或图形窗口命令。原生错误原样转换为协议错误，不使用静音文件、旧音频、其他音源或 UI 操作掩盖失败。
