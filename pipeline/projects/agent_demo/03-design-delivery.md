# 设计交付物（Design Delivery · 三件套）

> 契约说明：设计阶段的最终产出，开发 Agent 的**唯一设计输入**。
> 三件套 = ① Figma 链接+node ID ② tokens JSON ③ 页面截图。
> 本文件由设计 Agent 通过 Figma 官方 MCP 读回后填写，所有 node ID 必须真实可读回。

## 元数据

| 字段 | 值 |
|------|-----|
| 项目代号 | {{project_codename}} |
| 交付物版本 | v{{version}} |
| 对应需求书版本 | {{design_brief_version}} |
| Figma 文件 | {{figma_file_url}} |
| 生成日期 | {{created_at}} |
| 状态 | `draft` / `in-review` / `approved` |

## ① Figma 链接与 node ID

<!-- 开发 Agent 用 MCP 按 node ID 实时读取布局数据，不靠看图猜 -->

| 页面 ID | 页面名 | Node ID | MCP 读回验证 |
|---------|--------|---------|-------------|
| PG-01 | {{page_name}} | {{node_id}} | ✅ {{verified_at}} |

## ② Design Tokens

<!-- 从 Figma Variables 导出。开发阶段脚本化映射为 Flutter ThemeData/常量 -->

```json
{
  "color": {
    "primary": "{{value}}",
    "surface": "{{value}}",
    "error": "{{value}}"
  },
  "typography": {
    "titleLarge": { "fontSize": {{n}}, "fontWeight": "{{w}}" },
    "bodyMedium": { "fontSize": {{n}}, "fontWeight": "{{w}}" }
  },
  "spacing": { "xs": {{n}}, "s": {{n}}, "m": {{n}}, "l": {{n}} },
  "radius": { "m": {{n}} }
}
```

**Token 完整性核对**：
- [ ] 与 Figma Variables 一一对应，无遗漏
- [ ] 无 tokens 之外的硬编码设计值出现在设计稿中

### pending 与回填登记（强制 · P0 教训）

> ⚠️ 允许 `pending`（如 Figma 令牌失效导致读回/截图不可得），但**降级必须登记，否则必然被遗忘**。

| pending 项 | 原因 | 责任人 | 关闭条件 | 登记到回填表 |
|-----------|------|--------|---------|-------------|
| {{item}}（如 PG-01 node ID） | {{reason}} | designer | {{close_condition}} | ☐ 已登记 |

**规则**：
- 任一字段写 `pending` 而本表为空 → 校验失败（DR-10）
- 存在 pending 时，验收报告的 UI 一致性判定上限为 ⚠️
- 令牌/工具恢复后必须升版本（v1 → v2）回填，不得静默覆盖

## ③ 页面截图

<!-- 存放路径约定：pipeline/projects/<project>/design/screenshots/PG-xx.png -->
<!-- 这些截图同时是测试阶段 UI 快照对比的 golden master 基线 -->

| 页面 ID | 截图路径 | 与最终稿一致 |
|---------|---------|-------------|
| PG-01 | design/screenshots/PG-01.png | ✅ |

## 布局关键标注

<!-- MCP 读回后提取的、代码实现必须遵守的关键约束（开发容易做错的点） -->

| 页面 | 约束 | 值 |
|------|------|-----|
| PG-01 | {{constraint}} | {{value}} |

## 决策记录（Decision Log）

| 日期 | 版本 | 决策 | 理由 | 提出方 |
|------|------|------|------|--------|
| {{date}} | v1 | 初始版本 | - | 设计 Agent |

## 评审状态

| 动作 | 日期 | 意见摘要 | 影响页面 |
|------|------|---------|---------|
| 待确认 | - | - | - |

> 关卡 2 · 用户三态：✅ 通过（解锁开发阶段）/ 🔧 调整（仅改被质疑页面，重新生成+读回）/ ⏪ 打回（退回规划或需求书）
