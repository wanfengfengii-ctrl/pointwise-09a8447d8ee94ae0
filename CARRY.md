# 跨版读数承接

冷却工艺图改版后，检修员可以用指定旧批里的读数填入新版中来源确定的级。新版批次供现有事故冻结和回放使用。接班员可以按派生批次号核对每条承接读数的直接来源。V1 接口、初始化及直接批流程见 README.md。

## 公开调用

- `topology.eligible_stage_pairs(db, old_layout_id, new_layout_id)` 返回 `tuple[tuple[str, str], ...]`。每项是 `(旧级名, 新级名)`，先按旧版级序排列，同一旧级内按新版级序排列。返回两版之间所有通行语义等价的级对。此入口只读。
- `evidence.carry_observations(db, source_observation_id, new_layout_id)` 从指定批次取得源版和事故键。返回新登记的派生批次号 `int`。新批属于目标版，沿用源批事故键，按目标版级序存放承接读数，可直接调用 `freeze_incident(db, new_layout_id, derived_id)`。源批保持原样。
- `evidence.read_carry(db, derived_observation_id)` 返回字典，包含 `source_observation_id`、`old_layout_id`、`new_layout_id` 三个固定编号及 `matches`。`matches` 是按新版级序排列的 `(旧级名, 新级名, bool)` 元组序列，外层也是元组。无承接时为 `()`，三个编号仍保留。读取已发布的来源无需重新比较拓扑或对齐。

每条路线要求它引用的所有物理部件可用，每级要求至少一条路线通行。两版中同一物理部件 ID 使用同一个布尔变量，比较覆盖两级所涉变量的所有赋值。级名、路线名、路线顺序及参数修订号不决定语义等价。同一部件的重复出现取相同值。

一个对齐是由等价级对组成的序列，旧版位置和新版位置分别严格递增。两版所有级都参与，含无读数的级。只有在每一种最大基数对齐中都出现的同一个旧新级对，且旧级有明确读数，才写入派生批次及来源。即使多个可能来源的读数相同，仍按具体配对判断。`False` 是明确读数，未承接的级由 V1 读为 `None`。无承接时也登记合法空批。已有批次均可指定为源，来源记录指向本次指定的直接父批。源版和目标版相同时仍使用同一规则。允许全量重算。

沿用 V1 的连接、编号和初始化约定。对旧库执行既有初始化后，旧记录仍可按原接口读写。未知或非法编号报 `LookupError`。用直接批的号查询承接来源也报 `LookupError`。承接批次及来源一起原子提交，写入或提交失败保留 SQLite 错误，整次无留存，故障解除后可重试。后续参数更正、拓扑再发布、读数补报和关闭重开均不改变已发布的批次与来源。

## 手算和调用

`carry_examples.seed_cases(db)` 使用已初始化的连接，登记以下输入。`python3 -B -S -m carry_examples` 核对这些初始数据、临时数据库重开及提交失败夹具。`fail_observation_commit(db)` 可在验证时使插入读数批次的事务在提交阶段失败。

1. 旧版按序为 `Z:P`、`A:P`、`M:Q`，全批读数依次为 `True`、`False`、`False`。新版按序为 `R:P`、`S:Q∨(T∧Q)`。样例把 P 换为同一物理部件的新目录修订，并在路线中重复引用部件或等效路线。候选为 `(('Z', 'R'), ('A', 'R'), ('M', 'S'))`。两种最大对齐均包含 `M→S`，`R` 可分别对齐 `Z` 或 `A`。冻结新版派生批后，`R` 为 `None`，`S` 为 `False`。改用只含 `A=False` 的部分读数批时，`Z` 仍参与对齐，派生结果为空。另一个目标图只有 `Z:P∧T`，与旧图同名的级通行语义已经改变，无等价候选，也登记空批。
2. 另一个旧版按序为 `U:P`、`V:Q`，两级均读到 `False`。新版次序为 `V:Q`、`U:P`。两对都是候选，但最大只能配一对，两对各能出现在一个最大对齐里。新版两级均保持未观测。

第一组的调用示例。`db` 已按 README 初始化。

```python
from carry_examples import seed_cases
from evidence import carry_observations, freeze_incident, load_incident, read_carry
from topology import eligible_stage_pairs

cases = seed_cases(db)
assert eligible_stage_pairs(db, cases.old_layout_id, cases.new_layout_id) == (
    ('Z', 'R'), ('A', 'R'), ('M', 'S'),
)
batch_id = carry_observations(db, cases.full_source_id, cases.new_layout_id)
incident_id = freeze_incident(db, cases.new_layout_id, batch_id)
readings = load_incident(db, incident_id).observations
assert readings.reading_for('R') is None
assert readings.reading_for('S') is False
assert read_carry(db, batch_id) == {
    'source_observation_id': cases.full_source_id,
    'old_layout_id': cases.old_layout_id,
    'new_layout_id': cases.new_layout_id,
    'matches': (('M', 'S', False),),
}
```

## 核验与演示

沿用 `.pointwise-runtime.json` 的现有格式。`verify` 运行全部原回归及新增业务核验，核验失败以非零码退出。用手算案例核对候选、带歧义的承接、空批、冻结回放和来源。用提交失败夹具核对派生批次与来源均未留下，解除故障后重试。`demo` 调用真实入口，展示改画后的等价候选、冻结后明确为 `False` 和留为未观测的两级读数，以及补报并重开后按原派生号查到的来源。
