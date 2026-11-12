# SOP 动作类型参考（封闭集合）

> 调度器只识别以下 7 种动作。**新增动作类型 = 改 `_schema.json` + 改调度器 + 补测试**，
> 这是刻意设置的约束：动作越少，流程越可预测、越可测试。

---

## 1. `validate_inputs`

校验本阶段所需输入是否齐备且版本正确。

```yaml
- id: check-inputs
  action: validate_inputs
  params:
    requires:
      - path: pipeline/projects/{{project}}/00-project-brief.md
        deliverable: project_brief
        min_status: approved       # draft|in-review|approved
    forbidden_stale: [project_brief] # 这些交付物若为 stale 则失败
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `requires[]` | ✅ | 必须存在的输入 |
| `requires[].min_status` | ❌ | 最低状态要求（默认 `approved`） |
| `forbidden_stale[]` | ❌ | 若为 stale 直接失败（防"上游改了还往下跑"） |

**失败策略**：只能 `abort`（输入不齐不允许继续）。

---

## 2. `invoke_agent`

调用一个 Agent 执行本阶段主体工作，产出交付物。

```yaml
- id: draft-prd
  action: invoke_agent
  params:
    agent: planner
    agent_definition: pipeline/agents/planner.md
    output_path: pipeline/projects/{{project}}/01-prd.md
    output_manifest: pipeline/manifests/prd.manifest.yaml
    context:                       # 任务简报（只传必要信息，不传全量上下文）
      task: "把简报转化为 PRD"
      must_read:
        - pipeline/projects/{{project}}/00-project-brief.md
        - pipeline/templates/01-prd.template.md
      focus: ["用户故事", "页面清单", "统计口径", "任务拆解", "测试要点"]
    timeout_sec: 900
  on_fail: retry
  retry: { max_attempts: 2 }
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `agent` | ✅ | `planner｜designer｜developer｜tester｜acceptor` |
| `agent_definition` | ✅ | 该 Agent 的定义文件（调度器把内容注入 prompt） |
| `output_path` | ✅ | 产出文件路径 |
| `output_manifest` | ✅ | 产出后立即校验用 |
| `context.task` | ✅ | 本步任务描述 |
| `context.must_read[]` | ✅ | 必读文件（**白名单机制，防上下文膨胀**） |
| `context.focus[]` | ❌ | 本次重点关注项 |
| `timeout_sec` | ❌ | 超时（默认 600） |

**说明**：`context.must_read` 就是"任务简报"。P0 里靠主 Agent 自觉控制上下文，
现在由 SOP 显式声明——这是本方案相对 P0 的关键改进之一。

---

## 3. `validate_deliverable`

按 manifest 机械校验交付物结构。

```yaml
- id: check-prd-fields
  action: validate_deliverable
  params:
    deliverable: prd
    manifest: pipeline/manifests/prd.manifest.yaml
    fail_on: missing_section    # missing_section|missing_field|empty_table|any
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `deliverable` | ✅ | 交付物 id |
| `manifest` | ❌ | 默认 `manifests/<deliverable>.manifest.yaml` |
| `fail_on` | ❌ | 校验的严格程度（默认 `any`） |

**失败策略**：默认 `retry`（让 Agent 补齐），超过重试次数则 `abort`。

---

## 4. `check_rules`

对交付物或代码求值一组规则（质量门、DoD、规范检查）。

```yaml
- id: quality-gate
  action: check_rules
  params:
    ruleset: pipeline/gates/quality-gate.rules.yaml
    target: pipeline/projects/{{project}}/05-test-report.md
    rule_ids: [QG-01, QG-02]      # 省略则跑全部
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `ruleset` | ✅ | 规则文件 |
| `target` | ✅ | 被检查对象 |
| `rule_ids[]` | ❌ | 只跑指定规则 |

**失败策略**：质量门类规则只能 `abort`（不允许降级通过）。

---

## 5. `collect_human_input`

向人收集结构化输入（用于立项、增量需求录入）。

```yaml
- id: clarify
  action: collect_human_input
  params:
    questions:
      - id: weekly-target-max
        question: "「每周 N 次」的 N 上限？"
        suggested: "7（等效每天）"     # 建议值放首句，减少歧义
        type: single_choice
        options: ["1-7", "1-14", "其他"]
        required: true
    write_answers_to: pipeline/projects/{{project}}/00-project-brief.md
    answer_section: "已澄清记录"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `questions[]` | ✅ | 问题列表 |
| `questions[].suggested` | ❌ | **建议值（SOP 强制要求填写，P0 教训）** |
| `questions[].type` | ✅ | `single_choice｜multi_choice｜text｜confirm` |
| `write_answers_to` | ✅ | 答案落盘位置 |
| `answer_section` | ❌ | 落到哪个章节 |

---

## 6. `human_gate`

阶段结束，停下来等人做三态动作。**这是整个系统的核心原语。**

```yaml
- id: gate
  action: human_gate
  params:
    title: "关卡 1 · PRD 评审"
    actions: [approve, revise, reject]
    review_package:
      - pipeline/projects/{{project}}/01-prd.md
    review_package_extra:
      - "变更点高亮（返工时自动生成 diff）"
    require_comment_on: [revise, reject]
```

**行为约定**：
- 进入 gate 时状态置 `awaiting_review`，**流程必然停止**
- 收到 `approve` → 执行 SOP 的 `on_approve`
- 收到 `revise` → 状态置 `revising`，重跑本 SOP（版本 +1），**只改被质疑部分**
- 收到 `reject` → 执行 `on_reject`（含 `propagate_stale`），重开上游 SOP

> ⚠️ 除 `gate.enabled: false` 的辅助阶段外，**每个 SOP 必须恰好有 1 个人工 gate**。

---

## 7. `register_backfill`

登记降级产生的回填任务（P0 教训：降级即遗忘）。

```yaml
- id: register-token-backfill
  action: register_backfill
  params:
    item: "Figma design screenshots missing; UI baseline not established"
    owner: designer
    close_condition: "4 页 golden master 已导出且 MCP 读回校验通过"
    blocks_acceptance: false       # true 则验收报告 UI 项判定上限为 ⚠️
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `item` | ✅ | 回填事项 |
| `owner` | ✅ | 责任人（agent 或角色） |
| `close_condition` | ✅ | 可判定的关闭条件 |
| `blocks_acceptance` | ❌ | 是否影响验收判定上限 |

**规则**：任何 `on_fail: degrade` 的步骤**必须**在同 SOP 内有对应的 `register_backfill` 步骤，
否则 SOP 校验不通过（M2 的 `sops.py` 会强制检查这一点）。

---

## 动作 × 失败策略矩阵

| 动作 | 允许的 on_fail |
|------|---------------|
| `validate_inputs` | `abort` |
| `invoke_agent` | `retry` / `abort` / `degrade`（须配 backfill） |
| `validate_deliverable` | `retry` / `abort` |
| `check_rules` | `abort` / `degrade`（仅非质量门规则） |
| `collect_human_input` | `abort` |
| `human_gate` | —（无失败概念，等待即可） |
| `register_backfill` | `continue` |
