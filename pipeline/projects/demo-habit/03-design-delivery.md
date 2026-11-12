# 设计交付物（Design Delivery · 三件套）· demo-habit

## 元数据

| 字段 | 值 |
|------|-----|
| 项目代号 | demo-habit |
| 交付物版本 | v1 |
| 对应需求书版本 | v1 |
| Figma 文件 | https://www.figma.com/make/9E08Qy29MtOpevTi9NQpUK （Figma Make 生成，**读回校验待执行**：MCP OAuth 令牌过期） |
| 生成日期 | 2026-11-12 |
| 状态 | `approved`（v1 降级版；pending 项追踪回填，见下方降级说明） |

> **降级说明（v1）**：Figma MCP 令牌过期，读回校验与截图导出暂无法执行。
> 本版本产出：② tokens JSON（以需求书第 2 节为唯一权威值，开发可立即消费）；
> 待补：① node ID 读回验证、③ golden master 截图。修复令牌后回填升级为 v2。

## ① Figma 链接与 node ID

> ⚠️ 全部 `pending`——令牌修复后由设计 Agent MCP 读回验证并回填本表

| 页面 ID | 页面名 | Node ID | MCP 读回验证 |
|---------|--------|---------|-------------|
| PG-01 | 今日打卡（首页） | `pending` | ⏳ 待令牌修复 |
| PG-02 | 习惯编辑 | `pending` | ⏳ 待令牌修复 |
| PG-03 | 习惯详情 | `pending` | ⏳ 待令牌修复 |
| PG-04 | 设置 | `pending` | ⏳ 待令牌修复 |

## ② Design Tokens（权威值：02-design-brief v1 第 2 节）

> 开发 Agent 据此映射为 `app_theme.dart`；本 JSON 与需求书不一致时以需求书为准。

```json
{
  "color": {
    "primary": "#4F6BED",
    "surface": "#FFFFFF",
    "background": "#F6F7FB",
    "textPrimary": "#1A1D29",
    "textSecondary": "#8A90A3",
    "divider": "#ECEDF3",
    "error": "#E5484D",
    "success": "#30A46C",
    "habit": {
      "blue": "#4F6BED",
      "green": "#30A46C",
      "orange": "#F76B15",
      "purple": "#8E4EC6",
      "pink": "#D6409F",
      "teal": "#12A594"
    },
    "habitIconBgOpacity": 0.2
  },
  "typography": {
    "display":    { "fontSize": 28, "fontWeight": "w700", "letterSpacing": -0.5 },
    "titleLarge": { "fontSize": 20, "fontWeight": "w600" },
    "titleMedium":{ "fontSize": 16, "fontWeight": "w600" },
    "body":       { "fontSize": 14, "fontWeight": "w400" },
    "label":      { "fontSize": 12, "fontWeight": "w500" },
    "lineHeightMultiplier": 1.4
  },
  "spacing": { "xs": 4, "s": 8, "m": 16, "l": 24 },
  "radius": { "card": 16, "button": 12, "input": 12, "chip": 999 },
  "shadow": { "card": "0 2 8 rgba(26,29,41,0.04)" },
  "touchTargetMin": 44,
  "icon": { "presetCount": 12, "colorCount": 6 }
}
```

**Token 完整性核对**：
- [x] 与需求书第 2 节一一对应，无遗漏（14 色 + 5 字级 + 间距/圆角/阴影）
- [x] 习惯图标底色规则显式化（`habitIconBgOpacity: 0.2`，不单独建 token）
- [ ] Figma Variables 落库核对（⏳ 待令牌修复）

## ③ 页面截图（golden master）

> ⚠️ `pending`——MCP 令牌修复后从 Figma 导出，补齐后本表成为测试阶段 UI 快照对比基线

| 页面 ID | 截图路径 | 与最终稿一致 |
|---------|---------|-------------|
| PG-01 | design/screenshots/PG-01.png ⏳ | 待导出 |
| PG-02 | design/screenshots/PG-02.png ⏳ | 待导出 |
| PG-03 | design/screenshots/PG-03.png ⏳ | 待导出 |
| PG-04 | design/screenshots/PG-04.png ⏳ | 待导出 |

**测试阶段降级预案**：若验收前截图仍不可得，UI 快照对比项改为
「运行时截图 + 需求书逐页指令人工核对」，判定上限为 ⚠️（有条件通过），不阻断其余验收项。

## 布局关键标注

> 开发容易做错的点，需求书对应章节为准，此处汇总强调：

| 页面 | 约束 | 值 |
|------|------|-----|
| PG-01 | 已打卡卡片整体透明度 | 55%（不是只改按钮色） |
| PG-01 | 打卡按钮尺寸/描边 | 44pt 圆形；未打卡 = 习惯色 2pt 描边 |
| PG-01 | 打卡按钮用色 | **习惯色**，非全局 primary |
| PG-02 | 名称校验 | 1-20 字；非法时保存禁用 + error 描边 + 提示文案 |
| PG-02 | 步进器边界 | N∈1-7，到边界时对应按钮禁用（不禁用步进器） |
| PG-03 | 热力图 | 近 30 自然日，最早日在左上、今天在右下，格子 32pt 圆角 8 |
| PG-03 | 统计数字 | `display` 字级（28/w700），标签 `label` |
| 全局 | 触控热区 | ≥ 44×44pt |
| 全局 | 页面左右边距 | 16 |

## 决策记录（Decision Log）

| 日期 | 版本 | 决策 | 理由 | 提出方 |
|------|------|------|------|--------|
| 2026-11-12 | v1 | 降级发布：tokens JSON 先行，node ID/截图 `pending` | MCP 令牌过期；开发不应被设计验证工具阻塞，tokens 已有权威值 | 设计 Agent |
| 2026-11-12 | v1 | 截图缺失时 UI 快照对比降级为「截图+指令人工核对」，验收判定上限 ⚠️ | 保证测试阶段可执行，同时不让缺失静默通过 | 设计 Agent |

## 评审状态

| 动作 | 日期 | 意见摘要 | 影响页面 |
|------|------|---------|---------|
| ✅ 通过 | 2026-11-12 | 用户接受降级版：tokens 契约生效，node ID/截图 pending 追踪回填；解锁开发阶段 | - |

> **关卡 2（降级版）** · ✅ 通过（tokens 契约生效，pending 项追踪回填）/ 🔧 调整 / ⏪ 打回
