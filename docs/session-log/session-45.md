# Session 45: batch.run 归档保护

日期：2026-11-11。LabyRinth 的 V7 / GekiyakuV 整曲制作中，带扩展模板的 `batch.run` 被归档保护在外层拒绝，导致已支持的逐音编辑不能通过批量入口执行。

## 修复

- `native/ProjectArchivePreservation.cs`：只允许 `batch.run` 进入批量分发，不将 batch 当成普通可写操作放过其内容。
- `native/ScoreOperations.cs`：每个子操作在 `EditScore` 前调用 `CheckArchiveRequest`；继续拒绝嵌套 batch。首次失败停止，之前已经执行的操作保持原有语义，不宣称整个 batch 原子回滚。
- 未修改用户原工程、声库、MCP 注册或其他保护规则；源码改动尚未提交。

## 验证

- V7 原生语义预检 34 文件 / 218 引用 / 0 错误，V7 构建成功。
- 真实 stdio MCP 七音 GekiyakuV 模板工程：手写音符/曲线 batch 正例通过；包含嵌套 batch 的负例在索引1停止，后面的清空操作未执行；保存、归档、重开、声库与7个音符读回及非静音渲染通过。回执 `E:/VC/LabyRinth/production/vocal/gkv7/native_probe_75ef6c62a9.json`。
- 独立新建试句渲染后得到非空音素位置和可编辑范围，回执 `E:/VC/LabyRinth/production/vocal/gkv7/native_clean_30bd7cd799.json`。早期模板返回空范围的原因尚未单独定位。
- 实际作品后续以5段完成994个原生音节、三组 take 的编辑、保存、重开和渲染。未跑全部扩展工程组合、完整回归或 V6 构建；没有对最终作品做人耳试听。