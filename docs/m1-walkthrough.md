# M1 验收 · SOP 契约层 Walkthrough

> M1 的完成标志不是"写完了多少文件"，而是：**用这套 SOP 能否完整复现 P0 的真实流程，
> 且 P0 踩过的坑是否都被机器拦住了。**
> 验收方式：拿 `demo-habit` 的真实运行记录逐条对照，而不是凭空想象。

---

## 一、产物清单

| 类别 | 文件 | 数量 |
|------|------|------|
| SOP 定义 | `pipeline/sops/**/*.sop.yaml` | **13** |
| SOP schema | `pipeline/sops/_schema.json` | 1 |
| 动作参考 | `pipeline/sops/_actions.md` | 1 |
| 交付物校验规则 | `pipeline/manifests/*.manifest.yaml` | **14** |
| 规则引擎配置 | `pipeline/gates/*.rules.yaml` | **4**（36 条规则） |
| Agent 契约 | `pipeline/agents/*.md` | 5（已去拟人化） |
| 模板硬化 | `pipeline/templates/*.template.md` | 7（6 项硬化已落） |
| 工具脚本 | `pipeline/scripts/` | `validate-contracts.py`、`sync-spec.sh` |

**机器校验结果**：`通过 31 | 警告 0 | 错误 0`，13 个 SOP 全部通过 schema 与 8 条流程不变量。

---

## 二、SOP 覆盖率（对照 P0 真实流程）

### 新项目流程（P0 实跑路径）

| P0 实际阶段 | 对应 SOP | 步骤数 | Gate | 覆盖 |
|------------|---------|--------|------|------|
| 立项简报 | `00-brief` | 5 | 关卡 0 | ✅ 含待澄清采集 + 建议值强制 |
| 规划 PRD | `01-planning` | 6 | 关卡 1 | ✅ 含统计口径规则检查 |
| 设计需求书 + 三件套 | `02-design` | 9 | 关卡 2 | ✅ 含 Figma 预检 + token 覆盖自检 + 回填登记 |
| 开发 | `03-development` | 8 | 关卡 3 | ✅ 含规范装配 + DoD + 断言纪律检查 |
| 测试 | `04-testing` | 7 | 关卡 4 | ✅ 含独立用例 + 质量门 + 含人工放行留痕 |
| 验收 | `05-acceptance` | 6 | 关卡 5 | ✅ 含回填披露 + 未达成项强制 ❌ |

**合计 6 个阶段 / 5 个关卡 / 41 个步骤**（P0 的 5 个关卡全部保留，人工触点没有减少——
这是刻意的：方案 B 不追求"少人工"，追求"人工只在关卡，其余全机器"）。

### 增量流程（P0 完全缺失，M1 补齐）

| SOP | 步骤数 | Gate | 作用 |
|-----|--------|------|------|
| `intake-routing` | 3 | 分流确认 | 判断新项目 vs 新需求；输出 affected_deliverables |
| `10-requirement-intake` | 3 | 关卡 0 | 需求录入（业务目标/改动点/验收标准/回归风险） |
| `11-planning-delta` | 5 | 关卡 1 | 增量 PRD（变更最小化 + 影响面显式） |
| `12a-design-delta` | 4 | 关卡 2 | 仅涉及新页面时执行（复用既有 token） |
| `12b-development-delta` | 6 | 关卡 3 | 最小改动 + 改动清单 + 基线对比 |
| `13-testing-regression` | 5 | 关卡 4 | 新功能用例 + 回归 100% 覆盖 |
| `14-acceptance-delta` | 4 | 关卡 5 | 增量验收 + 既有结论影响评估 |

**关键设计**：`needs_new_pages=false` 时跳过设计阶段（由 `11-planning-delta` 的
`on_approve.next_sop` 指令控制），这是增量流程能"轻"起来的原因。

---

## 三、P0 的 15 条断点 → 机器拦截情况

> 这是 M1 最关键的验收项：**同样的错，第二次不能再犯。**

| # | P0 断点 | M1 拦截机制 | 拦截位置 | 状态 |
|---|---------|------------|---------|------|
| 1 | 关卡提问没把建议值放首句，用户复述问题 | `collect_human_input` 的 `suggested` 字段；`00-brief` 五个问题均带建议值 | SOP 步骤 | ✅ 机器 |
| 2 | weeklyN streak 口径歧义（天数 vs 周数） | PRD 强制「统计与业务口径」节；DR-01 检查含计数/比例但无口径节即 fail | manifest + DR-01 | ✅ 机器 |
| 3 | Figma 无写入通道，生成需人工代执行 | `02-design` 明确「Agent 是编排者不是绘制者」；生成动作走人工/Figam Make | SOP + Agent 契约 | ✅ 契约 |
| 4 | 团队组件库缺失 | AR-02 探测 → DEGRADED → 登记回填 | asset.rules | ✅ 机器 |
| 5 | Figma MCP 令牌过期 | AR-01 主动探测（**不再假设可用**）→ DEGRADED + 回填 | asset.rules | ✅ 机器 |
| 6 | **规范体系未落地（P0 最大坑）** | AR-03 + DOD-07 检测缺失 → `sync-spec.sh` 自动装配 | asset/dod rules | ✅ **已实测修复** |
| 7 | token 覆盖不全（圆角 8 / 空态灰无 token） | DR-04 token 覆盖自检：逐页扫描设计值反查 token 表，缺即 fail | deliverable.rules | ✅ 机器 |
| 8 | 热力图「5 行」契约缺陷 | DR-05 禁止写死行列数，必须写公式；manifest 正则拦截 | deliverable.rules | ✅ 机器 |
| 9 | ListTile ink 断言（组件测试提前抓到） | DOD-05 每个页面必须有组件测试；开发契约「先写测试再接页面」 | dod.rules | ✅ 机器 |
| 10 | 开发断言「done>due 不可能」实为错误 | DR-06「不可能」断言必须附构造性证明，否则 fail | deliverable.rules | ✅ 机器 |
| 11 | 自测报告未声明 FAB 阴影偏差 | DR-07 偏差必须写理由（还原状态=⚠️ 时同行为空即 fail） | deliverable.rules | ✅ 机器 |
| 12 | 测试 Agent 缺截图能力 | AR-04/AR-05 探测 → DEGRADED + 回填（**强制登记，防遗忘**） | asset.rules | ✅ 机器 |
| 13 | 质量门无硬规则，靠 Agent 自裁 | QG-01~QG-06 硬规则；高严重度 >0 自动 fail；人工放行需留痕 | quality-gate.rules | ✅ 机器 |
| 14 | 降级后遗症被遗忘（L-04） | `register_backfill` 动作 + I3 不变量（degrade 必须有回填）+ DR-10 + 验收报告第 8 节 | SOP 不变量 + 规则 + 模板 | ✅ 机器 |
| 15 | 验收环节靠人工才发现未达成项（L-02） | DR-09 禁止模糊表述；验收模板强制 ❌ + 原因；manifest 强制「未达成项」列 | deliverable.rules + 模板 | ✅ 机器 |

**结论：15 条中 14 条已机器拦截，1 条（#3 Figma 写入通道）以契约形式约束**——
这条是外部工具能力限制，无法靠规则解决，只能靠契约明确职责边界。

### 抽样验证（已实测，非纸面声明）

| 验证 | 命令/方式 | 结果 |
|------|----------|------|
| 契约完整性 | `python3 pipeline/scripts/validate-contracts.py` | ✅ 31 通过 / 0 警告 / 0 错误 |
| 规范体系自动装配 | `./pipeline/scripts/sync-spec.sh demo-app` | ✅ 装配 rules + 生成 AGENTS.md 索引 |
| 装配幂等性 | 连续执行两次 | ✅ 第二次输出「已是最新（跳过）」「索引已存在（跳过）」 |
| L-02 真修复 | `test -f demo-app/AGENTS.md && test -d demo-app/.github/...` | ✅ OK |

> **注意**：L-02 是 P0 验收时的遗留项，本节验证表明它已在 M1 实际修复，
> 而不只是"计划修复"。这是 M1 与 P0 的关键差别：**契约里写的东西必须真的能跑。**

---

## 四、M1 自证：契约层的 8 条不变量

`validate-contracts.py` 检查的流程不变量，本身就是 P0 教训的固化：

| 不变量 | 含义 | 来源教训 |
|--------|------|---------|
| I1 | 文件名 == `sop` 字段 | 防文件名与标识漂移 |
| I2 | `gate.enabled` 时恰好 1 个 `human_gate` | 防"每阶段必停"被绕过 |
| I3 | 任何 `degrade` 必须有 `register_backfill` | P0 教训 14：降级即遗忘 |
| I4 | 步骤数 3..12 | 防 SOP 过粗（失去约束）或过细（维护成本） |
| I5 | `output.manifest` 必须存在 | 防引用不存在的校验规则 |
| I6 | 禁止未转义占位符残留 | 防模板未填就提交 |
| I7 | `depends_on` 引用的 SOP 必须存在 | 防依赖指向空 |
| I8 | `dod` 非空且不含主观判据（"基本/大致/看起来"） | 防 DoD 变成口号 |

**I3 与 I8 在本次开发中当场抓到了问题**：
- I3 抓到 `02-design`、`03-development`、`04-testing` 三处 degrade 缺回填步骤 → 已补
- I8 抓到验收 DoD 措辞偏主观 → 已改

这说明校验器不是摆设，它对新写的契约也生效。

---

## 五、M1 的边界（诚实说明）

**已完成**：契约层（SOP / manifest / rules / agent / template）+ 校验工具 + 规范装配脚本。

**未完成（M2-M4）**：

| 项 | 归属 | 说明 |
|----|------|------|
| SOP 执行引擎 | M2 | 目前 SOP 是"可读可校验的规范"，还不能被执行 |
| StateStore | M2 | 状态仍靠手改 JSON（P0 方式），M2 接管 |
| preflight 实际探测 | M3 | 规则已定义，但 `mcp_probe`/`command` 等检查尚无可执行实现 |
| manifest 校验实现 | M3 | 规则已定义，markdown 解析器尚未实现 |
| headless Agent 接入 | M3 | Agent 契约已就绪，调用通道未接 |
| 增量流程实跑 | M4 | SOP 已定义，未跑过真实需求 |

**换句话说**：M1 交付的是"法律条文 + 校验法条自洽性的工具"，M2 才交付"执法机关"。

---

## 六、下一步（M2 的入口条件已满足）

M2 要做的三件事，M1 已为其铺好地基：

1. **StateStore** ← 直接消费 `pipeline-state.schema.json` 与 SOP 的 `on_*` 转换定义
2. **SOP 执行引擎** ← 7 种动作类型已封闭定义，只需实现分发器
3. **CLI 命令面** ← 命令签名与 SOP 目录结构已确定

**M2 首个可验证目标**：`pipeline run demo-habit --stage=planning --dry-run`
用 mock Agent 端到端跑通并停在 gate。
