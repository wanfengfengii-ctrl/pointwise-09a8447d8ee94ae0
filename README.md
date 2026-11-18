# 澄桥冷却服务事故复盘

澄桥工厂公用工程班组用这个库核对冷却服务事故。检修员从设备台账登记部件参数，从巡检表登记现场读数。工艺员按工艺图发布有序路线。复盘员用已经核实的部件实况定位受阻级，接班员按固定号码领取简报。共用部件在整版拓扑中沿用同一物理身份。新修订可以供下一次冻结使用，原事故和原简报仍可按号核对。

## 运行

使用 Python 3.11 标准库，从项目根目录运行。数据演示使用独立临时 SQLite 数据库。

```sh
python3 -B -S -m unittest discover -s tests -v
python3 -B -S -m demo_scenarios
```

`demo_scenarios` 依次运行原简报手算例和承接演示。`python3 -B -S -m tests.fixtures` 仍单独核对原简报价，`python3 -B -S -m carry_examples` 核对承接种子、临时库重开与提交失败夹具。

## 从登记到交班

公共函数以 `sqlite3.Connection` 为首参。每个连接在首次写入前依次调用 `AssetRepository(db).initialize()`、`LayoutRepository(db).initialize()`、`EvidenceRepository(db).initialize()` 和 `BriefRepository(db).initialize()`。各初始化仅补齐所属表，目录初始化为当前连接开启外键检查。写入口管理自己的事务，请在连接没有未完成事务时调用。

1. 检修员用 `put_asset(db, asset_id, description, availability)` 追加参数修订。身份为非空且首尾无空白的字符串，说明为字符串，可用率为 `[0, 1]` 内的 `Fraction`，无量纲。`get_asset_revision(db, revision_id)` 读历史，`get_current_asset_revision(db, asset_id)` 读最近一次成功登记的参数。精确分子分母以十六进制文本保存。
2. 工艺员用 `save_layout(db, stages)` 发布工艺图，输入为非空有序级序列。`Stage` 含非空的有序 `Route` 序列，路线含非空的有序 `AssetReference(asset_id, revision_id)` 序列。级名在同版唯一，路线名在所属级唯一。`load_layout_revision(db, revision_id)` 按原顺序读回，引用精确到每个部件修订。同版重复出现的物理部件使用同一个目录修订。
3. 检修员用 `put_observations(db, incident_key, layout_revision_id, readings)` 登记一批现场级读数。传入映射或 `(级名, bool)` 对的可迭代对象。每批描述本次所有已知级，空批表示全线未测。批次内重复级、拓扑外的级和非布尔值使整批被拒绝。
4. 复盘员用 `freeze_incident(db, layout_revision_id, observation_revision_id)` 冻结明确的父项。两个父项必须存在，读数所属拓扑号必须等于入参拓扑号。`load_incident(db, incident_id)` 读回固定上下文，`observations.reading_for(stage_name)` 返回 `True`、`False` 或未观测的 `None`。
5. 复盘员提交映射或 `(部件 ID, bool)` 对的可迭代对象。实况须恰好覆盖整版成员，缺项、冗余项、重复项或非布尔值均被拒绝。
6. `replay_incident(db, incident_id, component_states)` 返回固定上下文、实况、逐级结果、受阻级及读数差异。路线内全部部件可用才通行。级内至少一路通行才通行。整线要求所有级通行。即使前级受阻，仍计算所有后续级和各自全部可用路线。结果按工艺图次序展示，仅明确读数参与差异比较。实况以物理部件首次出现顺序归一化。
7. `issue_brief(db, incident_id, component_states)` 用同一回放入口核对并签发，提交成功后返回简报号。输入错误或 SQLite 写入及提交中止时，该次签发无可领取结果。
8. `read_brief(db, brief_id)` 领取原快照，包含事故键和三个固定父项号、级路线和部件修订引用、每级读数与通行结果、完整实况、受阻级和差异。目录更正、读数补报、拓扑再发布及数据库重开后可按原号码读取。

参数与结构错误分别由 `InvalidAsset`、`InvalidLayout`、`InvalidObservations`、`InvalidIncidentBinding`、`InvalidStateVector` 表示，均为 `ValueError` 子类。查无固定记录使用对应的 `LookupError` 子类 `UnknownAssetRevision`、`UnknownLayoutRevision`、`UnknownIncident` 或 `UnknownBrief`。简报存储错误保留 SQLite 错误类型，调用方可在故障解除后重试。

## 跨版读数承接

改版后可把指定旧批的明确读数承接进新版，规则见 CARRY.md。三项公开入口：

- `topology.eligible_stage_pairs(db, old_layout_id, new_layout_id)` 只读列出两版之间通行语义等价的 `(旧级名, 新级名)`，先按旧版级序、同一旧级按新版级序排列。级语义只看路线与部件 ID：级是各路线之“或”，路线是部件之“与”，同一物理部件共用一个布尔变量，因此重复部件、路线拆分与参数修订号都不改变等价判断。
- `evidence.carry_observations(db, source_observation_id, new_layout_id)` 登记派生批次并返回其号。两版全级序做一对一保序对齐，只有在每一种最大基数对齐中都出现的旧新级对才承接该旧级的明确读数（`False` 也算明确）；归属不确定的级留待实测。无承接也登记合法空批。源批不变，派生批沿用源批事故键、按目标版级序存放，可直接冻结。
- `evidence.read_carry(db, derived_observation_id)` 返回 `source_observation_id`、`old_layout_id`、`new_layout_id` 与按新版级序排列的 `matches`。按号读取已发布来源，不重新比较拓扑或对齐。未知号或用直接批号查询报 `UnknownCarry`，未知源批报 `UnknownObservation`（均为 `LookupError`）。

派生批次、`carry_batch` 与 `carry_match` 在同一事务内提交；写入或提交失败保留 SQLite 错误且整次无留存，故障排除后可重试。后续参数更正、拓扑再发布、读数补报与关闭重开均不改变已发布批次与来源。`python3 -B -S -m carry_examples` 核对种子、临时库重开与提交失败夹具。

## 手算例

取冷却部件 `X`、`A`、`B`。进水级 `intake` 有由 `X` 支撑的 `main` 和由 `A` 支撑的 `backup`。净化级 `polish` 的 `supply` 需要 `X` 与 `B`。若 `X=False`、`A=True`、`B=True`，进水仅备用路线可用，净化受阻，整线不通。若现场只登记 `polish=True`，唯一差异是净化现场通行、回放不通。进水读数仍为 `None`。

演示签发这份诊断，再更正 `X` 的参数并将现场补报提交为另一批读数。接班员重开后领取旧号，仍看到原两级工艺图、原参数引用和上述诊断。回归另用非字典序的级路线核对多处受阻、下游可行路线和明确不通的现场读数。
