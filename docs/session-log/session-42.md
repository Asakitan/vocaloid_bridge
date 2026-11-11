# Session 42: 破音（跳进滑音）、重叠渲染与桥接使用经验

日期：2026-11-11。接 session 39，同一首歌（`E:/VC/LabyRinth`，IA :[R]）。这一轮没有改桥接代码，只用既有操作（`batch.run`、`points_file`、`note.batch_update`、`controller.set`）做调教，并把实测行为补进文档。

## 要解决的问题

听感反馈：约 6 秒处的英文词（"echo"）破音。逐帧看是音高在两个相邻音符之间被引擎"扫"过去：一次 14 个半音的上行跳进，两个音符之间没有间隙，引擎在 100–200 ms 里连续滑过去，听起来是警笛式的扫频，而不是两个音高。

## 实测（IA :[R]，同一段反复渲染比较）

- **AI 音符的 `PitchTransitionStart/End` 与 `PitchDriftStart/End`**（0–1，默认 0.5）：对"零间隙的大跳进"，把到达音符的 `PitchTransitionStart` 和 `PitchDriftStart`、离开音符的 `PitchTransitionEnd` 和 `PitchDriftEnd` 都压低（Transition 取 0.0–0.1，Drift 取 0）后，滑音缩短到几乎听不出，落点也不再先欠后补（原先着陆音会偏低 1–2 个半音再爬上去）。这是 session 39 里"`PitchDriftStart` 设 0 会让过渡提前约 100 ms、只能用于句首"那条的补充：对跳进音符这种提前恰好是想要的，副作用是前一个音符的收尾变短。
- **`PitchDriftStart` 设 1.0 对跳进更糟**（着陆更差），没有采用。
- 本曲里按这个办法处理的是"间隙小于 90 ms 且跳进不小于 7 个半音"或"间隙小于 130 ms 且不小于 9 个半音"的 33 对音符；12 个半音以上用 0.0，其余用 0.1。先由规则列出候选，再逐对看频谱图决定保留，仍不对的三处另外手改：音符缩短（B 段 67.6 秒处 −12 个半音的零间隙下行，把前一个"-"延续音符从 480 tick 缩到 350 tick）；`PitchTransitionStart` 0.15 加显式 PitchBend 折线（E 段 178.7 秒处：翻转音原先是 2 个半音的前滑加 90 ms 的翻转斜坡，滑了约 280 ms）；音符结束处补 Dynamics 点（见下一条）。
- **句末爆音**：Dynamics 曲线在音符结束的那个 tick 就回到下一句的音量，而元音的收音还在发声，结果是休止后面冒出一个短促的有音高的"啪"（A 段第一句后，5.67 秒）。在休止里放一个值为 0 的 Dynamics 点即可。用 `h24_blip_scan.py` 这类"静音之后出现 15–130 ms 有音高的小岛"的扫描能找到同类问题，整曲扫一遍后只剩一处 −44.5 dB 的不可闻小岛。
- **`note.batch_update` 只带 `lyrics` 时只改文本，不重新生成音素**（用于把英文词音符的平假名文本改成片假名，音素保持不变）。它返回整张音符表，`controller.set` 返回整条曲线，几百个点或几百个音符的回执会非常长；大量写入时用 `batch.run` 的 `operations`，回执只有 `executed / total / failed_index`。
- **Take 配置会替换 PitchBend 曲线**：本曲的主唱与两条加厚用同一个 VPR 的不同 take 渲染（PitchBend ±27 单位的偏移），take 批处理用自己的 `points_file` 整条覆盖 PitchBend；先在 VPR 里手改的 PitchBend 点，如果没同步回 `points_file`，下一次 take 批处理就会把它冲掉。手改之后把数据文件一起改掉。
- **`project_render_part` 的输出在片段起点之前多 0.5 秒前导**，按时间对位时要减掉；`project_audio` 的混缩输出另有自己的起点偏移（本曲实测 0.494 秒），每个工程要测一次，不要沿用别的工程的数。
- 音高检测：pYIN 在 F#5 附近会出八度错误，谐波叠加（SHS）对八度滑动不敏感，YIN 对这条高音最稳；验证破音时用"相对原唱的多余滑动量"加"有音高小岛"两个指标，并且逐个对照频谱图，不要只看数字（第一轮扫描有几处"い"的误报，经频谱图确认是跟踪器伪影）。

## 校准数据（补充 session 39）

- Dynamics 114 约 +5 dB（64 为单位增益），衰减方向约兑现 77 %。
- Expression 50→85：0.4–1.5 kHz 约 0.154 dB/单位，1.5–4 kHz 约 0.36 dB/单位，与 session 39 的表一致。本曲 16 小节的"la la la"间奏里人声被乐器盖住，处理是把该处 Expression 提到 62，并在混音里对这 16 小节补一个 2.7 kHz 约 +4 dB 的均衡。
- PitchBend（PitchBendSens 24）每半音 341.33 单位；±27 单位约 ±8 音分，用于两条加厚的失谐。

## 没验证 / 没做

- 以上设置只在 IA :[R] 上测过；其他 AI 声库的 Transition / Drift 取值是否同样有效未知。
- 破音的判定仍是测量加看图，没有人耳试听；是否还有听得出的破音要听过才知道。
- 没有给这些经验新增自动化回归测试；证据在本机的 `curves/*_trans.json`、`output/labyrinth_sec*_v10/v11/v13.vpr` 和对应渲染，不随公开仓库发布。

## 补充（同一天稍后，echo 重新调音时的发现）

- **改动一个音符或曲线，同一个 part、同一个 take 里它之后的整段合成都会重新随机化**：新旧两次渲染在改动点之后波形差为 0 dB（完全不同），但音高轮廓和逐音符扫描分数不变。所以改完要对整个 part 重新扫描，不能只看改过的音。
- `S5Air` 的取值范围是 −100..100，`controller.set` 传 127 会被拒绝（`value must be an integer in -100..100`）；在一个 F#5 的短音上，Air 70（Expression 60）把"噪声/谐波"从 −34 dB 抬到 −19.5 dB，Air 100（同时改了 Expression 和 Dynamics）则变成没有音高的气声（电平低了约 9 dB），所以想要"带噪的喊声"只能取中间值，并用 Expression 和 Dynamics 把电平补回来。
- `note.update` 可以改 `start_tick` 和 `duration_tick`（整个音符前后移动、加长缩短），歌词和音素不受影响；`controller.set` 逐点写入是 upsert，不会删除相邻的点；take 配置（`controller.set` + `replace`）会整条换掉 PitchBend，其余曲线（Dynamics、Expression、S5Air、S5Character）保留在 VPR 里。
- 一个我自己的构建器 bug 值得提醒用这个桥画曲线的人：把几条曲线（起音、颤音、收音）写进同一个按 tick 排序的列表时，重叠区间的点会交替出现，PitchBend 在几个 tick 内上下跳几百单位，渲染里是音高抖动；重叠的曲线要先相加再写点。

## 补充 2（同一天晚些时候）

- **`output/` 不是仓库，一小时后会被清空**：`vocaloid_bridge/cleanup.py` 随 MCP 服务启动一个后台线程，永久删除 `output/**` 里超过 3600 秒的文件（环境变量 `VOCALOID_TEMP_CLEANUP=0` 关闭，`VOCALOID_TEMP_MAX_AGE_SECONDS` 调整时限，`VOCALOID_TEMP_CLEANUP_INTERVAL_SECONDS` 调整间隔）。本曲一直把 VPR 版本和整段渲染留在 `output/` 里，某次服务重启之后的清理（16:40）把现行的两个 VPR、两个和声工程和一批渲染都永久删掉了（不进回收站）。要长期保留的 VPR / 渲染，保存后立刻复制到工程目录；需要保留时先关掉清理或加大时限。这条行为在文档里写在 `cleanup.py` 的模块说明里，使用说明里没有提醒，值得在 README 的"输出目录"处补一句。
- **`S5Character` 在 IA :[R] 上作用很强**：在 build 末尾约 D#6 的喊声音符上，Character 0 → 50 把 1.5–4.5 kHz 相对 0.2–1.5 kHz 的倾斜抬高到 +5.8 dB（约 0.5 dB / 单位），过头了；取 27 并配合 Dynamics 88、Air 60，渲染后的倾斜接近原唱的 +1.7 dB 还差约 3.4 dB，其余在混音里补（3.2 kHz 钟形 +4.5 dB）。Character 做的是渐变而不是开关，按 tick 渐变写比整音符一个值更自然。
- 同一类做法的共同点：先用同一把尺（噪声/谐波比、1.5–4.5 kHz 倾斜、电平）量原唱与渲染，再决定动 Air / Character / Expression / Dynamics 的哪个；每动一次整段重新渲染后重新量。
