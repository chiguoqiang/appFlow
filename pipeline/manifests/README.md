# Manifest 格式规范（交付物机械校验规则）

> Manifest 把"模板字段齐不齐"从肉眼检查变成机器可执行规则。
> `pipeline validate <project> --deliverable=<id>` 读取对应 manifest 并逐条求值。

## 文件结构

```yaml
manifest: prd                 # manifest 标识
deliverable: prd              # 对应交付物 id
default_path: pipeline/projects/{{project}}/01-prd.md
description: PRD 结构校验

sections:                     # 必需章节，按出现顺序检查（顺序不强制，存在性强制）
  - id: user-stories
    title: 用户故事            # markdown 二级标题文本（精确前缀匹配）
    type: table               # table | list | text | mermaid
    required: true
    columns: ["#", 用户故事, 优先级, 验收标准]
    min_rows: 1
    row_id_pattern: "US-\\d+"  # 首列必须匹配（可选）

rules:                        # 全局规则
  forbid_placeholder: true    # 禁止残留 {{placeholder}}
  forbid_empty_section: true  # 禁止标题存在但内容为空
  max_placeholders: 0
```

## 校验项说明

| 校验项 | 含义 | 违例示例 |
|--------|------|---------|
| `sections[].required` | 章节必须存在 | 缺「统计口径」节 |
| `sections[].type: table` | 必须是 markdown 表格 | 写成了散文 |
| `sections[].columns` | 表头必须包含这些列 | 任务拆解缺「验收方式」列 |
| `sections[].min_rows` | 表格数据行下限 | 功能清单只有表头 |
| `sections[].row_id_pattern` | 首列编号格式 | 页面清单用了「第1页」而非 `PG-01` |
| `sections[].must_contain` | 章节正文必须含这些字串 | 简报缺「明确不做」 |
| `sections[].forbid` | 正则黑名单 | 残留 `{{xxx}}` |
| `rules.forbid_placeholder` | 全文禁占位符 | 模板未填完就提交 |

## 校验强度（`--fail-on`）

| 级别 | 触发项 |
|------|--------|
| `missing_section` | 仅缺失章节即失败 |
| `missing_field` | 额外包含列缺失、行数不足 |
| `any`（默认） | 全部规则，含占位符与空内容 |

## 设计原则

1. **只校验"有没有"，不校验"好不好"** —— 内容质量由规则引擎（`gates/*.rules.yaml`）与人工关卡负责
2. **宁可宽松** —— 误报会让人绕过校验，那比不校验更糟
3. **每条规则必须可解释** —— 校验失败时输出「缺哪个章节/哪一列/第几行」，而不是只说"不通过"

## 与 SOP 的关系

SOP 的 `validate_deliverable` 动作引用 manifest；`output_manifest` 字段让 Agent 产出后立即自检。
两者共用同一份 manifest，保证"Agent 自检"与"调度器验收"标准一致。
