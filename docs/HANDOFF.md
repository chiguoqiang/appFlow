# 换机交接文档（HANDOFF）

> **用途**：换电脑/换协作者时，从这里开始。本文档是唯一权威的现状说明，
> 不依赖任何本地会话记忆。
>
> 最后更新：2026-11-12（M2 完成）

---

## 0. 一句话说明这是什么

一套「**输入想法 → 输出可运行 App**」的 AI 软件生产线，采用**方案 B（SOP 流水线工厂）**：
流程写成可版本化的 YAML 契约，由 Python 调度器强制执行；Agent 只是 SOP 里的一个动作。

已用它端到端产出过一个真实 App（习惯打卡，`demo-app/`）。

---

## 1. 换电脑后 5 步复现

### 1.1 环境依赖

| 依赖 | 版本要求 | 检查命令 |
|------|---------|---------|
| Python | **3.10+**（开发用 3.12.14） | `python3.12 --version` |
| uv（推荐） | 任意 | `uv --version` |
| Flutter | stable（开发用 3.44.9 / Dart 3.12.2） | `flutter --version` |
| Xcode + iOS 模拟器 | 仅做 iOS 冒烟时需要 | `xcrun simctl list devices booted` |
| Figma MCP | 仅设计阶段完整链路需要（当前令牌过期） | — |

### 1.2 重建 Python 环境

```bash
cd pipeline/cli
uv venv --python python3.12 .venv
uv pip install --python .venv/bin/python typer pydantic pyyaml pytest

# 让 `pipeline` 命令可用（无需 pip install）
export PATH="$PWD:$PATH"
pipeline version        # 应输出 pipeline-cli 0.2.0

# 验证测试
PYTHONPATH=src ./.venv/bin/python -m pytest tests/ -q
```

> 💡 把 `export PATH="<repo>/pipeline/cli:$PATH"` 写进 `~/.zshrc` 就不用每次都设。

> ⚠️ `.venv` 不入版本库（见 `.gitignore`），必须重建。

### 1.3 重建 Flutter 依赖

```bash
cd demo-app
flutter pub get
flutter analyze   # 应输出 No issues found!
flutter test      # 应输出 All tests passed!（65 项）
```

### 1.4 重建规范体系（重要）

`demo-app/.github/skills/flutter-dev-playbook/rules/` **不入版本库**，因为它由外部 skill 装配：

```bash
cd /path/to/project
./pipeline/scripts/sync-spec.sh demo-app
# 需要 skill 存在于以下任一位置：
#   .github/skills/flutter-dev-playbook/rules
#   ~/.agents/skills/flutter-dev-playbook/rules
#   ~/.claude/skills/flutter-dev-playbook/rules
```

> 若新机器没有该 skill：从原机器拷 `~/.agents/skills/flutter-dev-playbook/` 过去。
> 脚本是幂等的，重复执行安全。

### 1.5 验证整体健康

```bash
# 契约自检（应输出：通过 31 | 警告 0 | 错误 0）
python3 pipeline/scripts/validate-contracts.py

# 调度器测试（应全绿）
cd pipeline/cli && PYTHONPATH=src ./.venv/bin/python -m pytest tests/ -q

# 项目状态
PYTHONPATH=src ./.venv/bin/python -m pipeline_cli.main status demo-habit
```

---

## 2. 当前进度

### 已完成

| 阶段 | 内容 | 状态 |
|------|------|------|
| **P0** | 用手工方式端到端跑通一个真实 App（demo-habit） | ✅ 完成 |
| **M1** | SOP 契约层：13 SOP / 14 manifest / 4 规则集 36 条 / 5 Agent 契约 / 7 模板 | ✅ 完成 |
| **M2** | 调度器内核：StateStore / SOP 引擎 / Gate 三态 / manifest 校验 / 规则引擎 / CLI | ✅ **完成** |

### M2 已通过的验收

```
$ pipeline init smoke --flow=new_project
✓ 已初始化 smoke（new_project）  阶段: 6 · 交付物: 7

$ pipeline run smoke --stage=brief --answer core-idea=... 
▶ SOP 00-brief · 立项简报
    ✓ 已记录 5 项回答
    ✓ planner 产出 00-project-brief.md
    ✓ manifest 校验通过（8 章节）
    ⏸ 关卡 0 · 立项确认 已就绪

$ pipeline gate smoke --stage=brief --action=approve
✓ 阶段 brief → approve  版本: v1  下一阶段: planning

$ pipeline run smoke --stage=planning
▶ SOP 01-planning · 规划（PRD）
    ✓ 输入齐备（1 项）
    ✓ planner 产出 01-prd.md
    ✓ manifest 校验通过（12 章节）
      ✓ DR-01 统计口径: pass
      ✓ DR-02 页面编号: pass
      ✓ DR-03 P0功能有测试要点: pass
    ⏸ 关卡 1 · PRD 评审 已就绪

$ pipeline gate smoke --stage=planning --action=reject --comment="目标用户理解错了"
✓ 阶段 planning → reject  交付物状态: stale
  标记过期: design_brief, design_delivery, dev_report, test_report, acceptance_report
  重开: 00-brief
```

**测试：62 项全绿**（`test_checks` 30 + `test_state` 16 + `test_engine` 16）

### 后续里程碑

| 里程碑 | 内容 | 预估 |
|--------|------|------|
| **M3** | preflight 真实探测（AR-01~10 实现）+ headless Agent 接入 + 截图链路 | 1.5 周 |
| **M4** | 增量流程实跑（建议用 demo-app 的 4 个遗留缺陷当第一个真实需求） | 1.5 周 |
| M5（可选） | Portal 组织视图（只读看板 + 审批按钮） | — |

### M2 期间发现并修复的真实缺陷（记录价值）

| 缺陷 | 影响 | 修复 |
|------|------|------|
| `main.py` 缺 `__main__` 入口 | `python -m pipeline_cli.main` 静默无操作（exit 0） | 补 `if __name__ == "__main__": app()` |
| `00-brief` SOP 从未生成简报文档 | 只追加答案，`validate-brief` 必然失败 | 补 `draft-brief`（invoke_agent 整理成模板全字段） |
| 一份 SOP 多个 `invoke_agent` 共用交付物 → 版本重复 +1 | brief 从 v1 变 v2 | 仅当步骤产出==SOP 主输出时才升版本 |
| `paths.state_file` 抛「项目不存在」而非「状态文件不存在」 | 错误信息误导 | `project_dir(must_exist=False)` |
| 关卡标题未透传到 CLI | 输出显示「关卡 等待人工确认」 | `needs_human` payload 补 title |

> 这些缺陷都是 **M2 一跑就暴露的**——M1 的契约靠人工审查看不出来。
> 印证了「契约必须能被机器执行验证」这个判断。

---

## 2.5 两种使用模式（重要）

调度器的 `invoke_agent` 动作有两种实现，决定了你能用它做什么。

### 模式一 · mock 生成（当前默认）

```bash
pipeline run my-app --stage=planning
```

| 能验证 | 不能得到 |
|--------|---------|
| 流程顺序、关卡暂停、stale 传播 | ❌ 可用的 PRD 内容 |
| manifest 结构校验、规则引擎 | |
| 断点续跑、失败策略 | |

`MockInvoker` 只管让**结构合法**（章节齐、表格列对、编号格式对），内容全是占位符
（`#4F6BED`、`本节说明「产品概述」的内容。`）。**适合演示流程机制，不适合真做项目。**

### 模式二 · 混合模式 ⭐ 做真项目用这个

**内容由人或 IDE 内的 Agent 写，机器负责校验与状态管理。**

```bash
# ① 建项目
pipeline init my-app

# ② 手工（或在 IDE 里让 AI 生成）写好交付物
vim pipeline/projects/my-app/00-project-brief.md

# ③ 提交 → 机器按 manifest 校验
pipeline submit my-app --stage=brief

# ③' 如果校验失败，会精确告诉你缺什么：
#     ✗ manifest 校验失败（10 项）
#       - user-stories: 首列值「1」不匹配 US-\d+
#       - features: 缺少章节「功能需求」
#     → 补齐后重新 submit

# ④ 人工关卡
pipeline gate my-app --stage=brief --action=approve

# ⑤ 下一阶段重复 ②~④
```

**这个模式相对 P0（纯对话）多出两道保险**：

1. 交付物结构不合规 → **被 `submit` 拦住**（不用肉眼查字段）
2. 关卡状态 / stale 传播 → **由状态机记录**（不用手写 JSON）

**已实测的完整闭环**：

```
手工写残缺 PRD → submit → ✗ 拦住 10 项问题（含"首列应为 US-1"）
补齐合规 PRD  → submit → ✓ 12 章节通过 → v2 in-review
               → gate approve → ✓ approved → 推进 design
```

### 模式三 · 全自动（M3 之后）

```bash
pipeline run my-app --stage=planning --agent=headless
```

需要 M3 接入 Claude Code headless。**这是最终目标，但目前不可用。**

---

## 3. 目录导航

```
project/
├── HANDOFF.md                  ← 本文档（入口）
├── .gitignore
├── demo-app/                   ← 流水线产出的真实 Flutter App
│   ├── lib/                    19 个源文件（core/models/data/domain/providers/theme/widgets/pages）
│   └── test/                   9 个测试文件，65 项测试全绿
├── pipeline/                   ← 生产线本体
│   ├── sops/                   ★ 流程定义（13 个 .sop.yaml + _schema.json + _actions.md）
│   │   ├── new-project/        6 个：00-brief ~ 05-acceptance
│   │   ├── new-requirement/    6 个：intake-routing + 10 ~ 14（增量流程）
│   │   └── intake-routing.sop.yaml
│   ├── manifests/              ★ 交付物字段校验规则（14 份）
│   ├── gates/                  ★ 4 套规则集（36 条）：quality-gate / deliverable / dod / asset
│   ├── agents/                 ★ 5 份执行者契约（去拟人化：职责边界 + 红线 + gate 响应）
│   ├── templates/              7 份交付物模板（含 6 项 P0 教训硬化）
│   ├── scripts/
│   │   ├── validate-contracts.py   契约自检（含 8 条流程不变量）
│   │   └── sync-spec.sh            规范体系自动装配
│   ├── cli/                    ★ M2 调度器（Python）
│   │   ├── src/pipeline_cli/   errors/paths/models/state/sops/checks/agents/actions/engine/gate/main
│   │   └── tests/              conftest + test_checks + test_state + test_engine
│   └── projects/
│       └── demo-habit/         P0 一次完整运行的 6 份交付物 + pipeline-state.json
└── docs/
    ├── HANDOFF.md              ← 本文档
    ├── runbook.md              P0 断点日志（15 条）+ 复盘结论
    ├── m1-walkthrough.md       M1 验收：15 条断点 → 机器拦截对照表
    └── p1-backlog.md           缺陷与改进项清单
```

**★ 标记的是核心资产**：流程知识全在这里，其余是产物。

---

## 4. 常用命令速查

### 调度器（M2）

先配置命令入口：
```bash
cd /path/to/project/pipeline/cli
export PATH="$PWD:$PATH"      # 让 pipeline 命令可用
```

```bash
# 初始化项目
pipeline init my-app --flow=new_project

# 方式一：mock 自动生成（验证流程机制，内容为占位符）
pipeline run my-app --stage=brief \
  --answer core-idea="一句话想法" --answer target-users="目标用户" \
  --answer mvp-features="功能清单" --answer out-of-scope="不做的事" \
  --answer tech-constraints="技术约束"

# 方式二：混合模式（自己写内容 → 机器校验 → 进关卡）⭐ 推荐
#   1. 手工编辑 pipeline/projects/my-app/01-prd.md
#   2. 提交校验
pipeline submit my-app --stage=planning

# 查看状态
pipeline status my-app -v

# 关卡三态
pipeline gate my-app --stage=planning --action=approve
pipeline gate my-app --stage=planning --action=revise --comment="目标用户要改"
pipeline gate my-app --stage=planning --action=reject --comment="方向错了"

# 校验交付物（含内容规则）
pipeline validate my-app --deliverable=prd --rules

# 报告 / 资产检查
pipeline report my-app
pipeline preflight my-app
```

### 契约自检
```bash
cd /path/to/project
python3 pipeline/scripts/validate-contracts.py
```

### Flutter
```bash
cd demo-app
flutter analyze && flutter test
flutter run -d <simulator-id>
```

---

## 5. 关键架构决策（不要重新讨论）

这些都是经过验证或明确取舍的结论，改之前先读理由。

| 决策 | 理由 | 位置 |
|------|------|------|
| **方案 B（SOP 工厂），不做"数字员工"拟人化** | 可控、可审计、可测试；拟人化只带来叙事快感无工程收益 | `pipeline/sops/_actions.md` |
| **SOP 动作类型只有 7 种（封闭集合）** | 动作越少越可预测；新增动作必须改 schema + 改引擎 + 补测试 | 同上 |
| **每个 SOP 恰好 1 个人工 gate，绝不自动连跑** | 全自动不可控（P0 已否决纯 Agent 路线）；校验器 I2 强制 | `validate-contracts.py` |
| **校验规则写成 YAML 数据，不写进 prompt** | 可机器执行、可版本 diff、可被脚本消费（也是 IDE Hook 集成的前提） | `pipeline/gates/` |
| **未实现的规则返回 `skip`，绝不静默 `pass`** | 静默通过与不校验等价，且更危险 | `checks.py` |
| **交付物校验分两层：manifest 查"有没有"，rules 查"写得对不对"** | 关注点分离，误报率低 | `manifests/README.md` |
| **降级必须登记回填（I3 不变量）** | P0 教训：Figma 令牌过期降级后，UI 基线缺口差点被遗忘 | `sops/_schema.json` |
| **`revise` 与 `reject` 语义严格区分** | revise 增量改（版本+1，重跑本阶段）；reject 认为上游有问题（stale 传播 + 重开上游） | `gate.py` |
| **Python 做调度器，不用 Dify 做内核** | Dify 无 human-in-the-loop 阻塞原语、Code 节点无文件系统；但它适合做 Agent 层（M3+ 可选） | 会话讨论结论 |
| **开发阶段不嵌套子 Agent** | 嵌套导致上下文失控、错误定位困难；改用 AGENTS.md 规范驱动 | `agents/developer.md` |

---

## 6. 已踩过的坑（新环境注意）

| 坑 | 现象 | 解法 |
|----|------|------|
| `~/.agents/skills/.../rules` 不存在 | `sync-spec.sh` 报"未找到 rules" | 从原机器拷贝该 skill 目录 |
| Python 3.9 缺 pytest | 系统 python 是 3.9.6 | 必须用 3.12（见 1.2） |
| pip 装包 TLS 证书错误 | `Could not find a suitable TLS CA certificate bundle` | 改用 `uv pip install` |
| `flutter test` 首次报 `Undefined name 'json'` | 生成代码与手写代码不一致 | 跑 `dart run build_runner build` |
| iOS 模拟器 `simctl` 无法点击 | 只能截首页，无法驱动多页 | 需 `integration_test`（M3/M4 待补） |
| Figma MCP 403 Token expired | 设计阶段读回校验中断 | 刷新 OAuth 令牌；临时走 `pending` + 回填登记 |

---

## 7. demo-app 的遗留缺陷（M4 建议用它当第一个增量需求）

| # | 缺陷 | 严重度 | 修法 |
|---|------|--------|------|
| L-01 | 详情页删除习惯后停在「习惯不存在」死页面 | 🔴 高 | `Navigator.popUntil((r) => r.isFirst)` |
| L-03 | 进度 chip 出现「今日 1/0」（done > due） | 🟡 中 | `todayProgress()` 中 `due` 统计口径纳入「今日已打卡」 |
| L-05 | FAB 阴影超设计规范 | 🟢 低 | `elevation: 0` |
| L-06 | 前台跨 0 点不自动刷新 | 🟢 低 | App resume 时 `ref.invalidate(clockProvider)`，或接受为已知限制 |
| L-02 | 规范体系未落地项目内 | — | ✅ **已修复**（`sync-spec.sh`） |

> **这 4 个缺陷是 M4 的理想试金石**：真实、体量小、覆盖「增量流程」全链路，修完既是产品优化也是流程验证。

---

## 8. 给接手 Agent 的第一条指令建议

```bash
读 docs/HANDOFF.md，然后：
1. 跑第 1.5 节的 3 条验证命令，确认环境健康
2. 汇报当前状态（不要直接开始 M3）
3. 若要继续：M3 的第一步是「preflight 真实探测」——实现 asset.rules.yaml 的 AR-01~AR-10
```

---

## 9. 版本库建议

当前**非 git 仓库**。建议：

```bash
cd /path/to/project
git init
git add .
git commit -m "chore: P0 + M1 完成，M2 调度器内核 8.5/9"
```

`.gitignore` 已配好，会排除 `.venv`、`build/`、装配型 rules 等可重建内容。

若用云盘同步（iCloud/OneDrive），**务必排除** `pipeline/cli/.venv`、`demo-app/build`、
`demo-app/.dart_tool`——这些目录文件数极多，会让同步极慢甚至卡死。
