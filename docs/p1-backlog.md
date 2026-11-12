# P1 Backlog · AI 移动应用生产线

> 来源：P0（demo-habit 全流程实跑）的验收遗留 + 流水线断点复盘。
> 排序原则：先修「让流水线本身可信」的事，再修「demo 的功能缺陷」，最后做「平台化」。

---

## 一、必修缺陷（demo-habit，约 1 小时）

低成本高价值，修复后 demo 可作为后续项目的参考样板。

| # | 项 | 位置 | 修法 | 验证 |
|---|----|------|------|------|
| FIX-01 | **L-01 · 删除习惯后死页面**（高） | `lib/pages/edit_habit_page.dart` `_confirmDelete()` | 删除成功后 `Navigator.popUntil((r) => r.isFirst)`，或在 PG-03 检测 `habit == null` 时自动 pop | QA 用例 TC-04 转绿 |
| FIX-02 | **L-03 · 进度 chip `done > due`**（中） | `lib/domain/habit_stats.dart` `todayProgress()` | `due` 统计口径包含「今日已打卡」：`if (isDueToday(...) || isCheckedToday(...)) due++` | QA 用例 TC-02 转绿 |
| FIX-03 | L-05 · FAB 阴影超规范（低） | `lib/pages/home_page.dart` | `FloatingActionButton(elevation: 0, focusElevation: 0, hoverElevation: 0, highlightElevation: 0)` | PG-01 截图与需求书「无其他阴影」一致 |
| FIX-04 | L-06 · 前台跨天不刷新（低，待产品决策） | `lib/providers/habit_provider.dart` | App resume 时 `ref.invalidate(clockProvider)` | 跨天 mock 测试 |

**DoD**：`flutter analyze` 零告警 + `flutter test` 全绿（含 `test/qa/` 用例）+ 重跑一次 QA 用例 17/17。

---

## 二、流水线基础设施（P1 第一优先级，比修 demo 更重要）

### 2.1 启动资产装配检查（P0 架构级收获）★最高优先

**问题**：Agent 定义声明依赖了各种资产，但无环节装配它们 → 3 个阶段分别踩坑。

**方案**：新增 `pipeline/scripts/preflight.sh`（或 Agent 定义中的强制前置步骤），逐项探测：

| 检查项 | 探测方式 | 失败处理 |
|--------|---------|---------|
| Flutter 环境 | `flutter --version` | 中止，提示安装 |
| iOS 模拟器 | `xcrun simctl list devices booted` | 尝试 boot，失败则降级到真机说明 |
| Figma MCP 连通性 | 尝试读一个已知 fileKey | **降级**：设计走「自建 token 模式」，记录回填任务 |
| 团队组件库/Variables | Figma MCP 读 library | **降级**：项目内自建 token 集 |
| 规范体系文件 | 检查 `demo-app/AGENTS.md` 与 `rules/` | **可自动装配**：从 `~/.agents/skills/flutter-dev-playbook/rules` 拷入并生成索引 |
| 截图工具链 | `integration_test` 是否配置 | **降级**：UI 对比走人工核对，登记回填 |

**产出**：`preflight-report.md`，逐项记录 `OK / DEGRADED / BLOCKED` + 对应降级策略。

### 2.2 规范体系自动落地

**问题**：简报硬约束「遵循 flutter-dev-playbook / AGENTS.md 三级 Rules」在 P0 **未达成**。

**方案**：把「复制 rules 到项目 + 生成根 `AGENTS.md` 索引」做成工程初始化的显式步骤（T-01 的一部分），并在 DoD 中加入「根 `AGENTS.md` 存在」检查。

### 2.3 截图工具链（验收自动化的前置依赖）

**问题**：golden master（Figma 令牌）+ 运行时截图（无点击驱动）双侧都缺，UI 对比只能人工核对 1/4 页。

**方案**：
1. `integration_test/` 四页自动导航截图脚本（`flutter drive`）
2. Figma 令牌修复后导出 4 页设计截图作为 golden master
3. 对比脚本：像素 diff + 阈值判定（可用 `pixelmatch` 类实现或 `image` 包）

### 2.4 契约模板修订（6 项，来自 runbook）

| 模板 | 修订 |
|------|------|
| 02-design-brief | ① 增加「token 覆盖自检」：逐页反查设计值 → token，缺失即补<br>② 容量/网格类规约改写为公式（如 `rows = ceil((leading + days) / 7)`） |
| 03-design-delivery | node ID / 截图字段原生支持 `pending`，并要求在 `pipeline-state` 有回填追踪字段 |
| 04-dev-report | 增加规则：「凡断言『不可能发生』必须附构造性证明，否则标注为假设待验证」 |
| 05-test-report | 第 1 节加入**质量门硬规则**：高严重度未修复 = 自动判定不通过（不再由 Agent 主观裁定） |
| 06-acceptance-report | 增加「未达成项须显式标注 ❌ 并附原因」的强制字段（本次 L-02 就是靠人工发现） |
| 全部关卡 | 提问把「建议值」放问题首句；Portal 用单选替代自由输入 |

### 2.5 开发 Agent DoD 强化

- 先写组件测试再接页面（P0 已验证能提前抓渲染层缺陷）
- 设计偏差必须声明（BUG-03 是未声明偏差）
- 每完成一个任务即跑 analyze + test（P0 已执行，需固化）

---

## 三、平台化（P1 后半 → P2）

| 项 | 内容 | 依赖 |
|----|------|------|
| 阶段脚本化 | 把 P0 的手工动作固化为可重跑脚本（`pipeline run --stage=planning`） | 2.1 完成 |
| 状态机 SDK | `pipeline-state.json` 读写 + 校验 CLI（避免手写 Python） | - |
| Git/PR 集成 | 开发阶段产出真实 PR，code review 关卡挂 PR 链接 | Git 仓库初始化 |
| Portal MVP | 表单化输入简报、进度可视化、评审包渲染（内嵌 Figma 预览） | 阶段脚本化 |
| Figma 写入探索 | 「需求书 → Figma Make 提示词」转换模板（减少人工翻译损耗） | 令牌稳定可用 |

---

## 四、P0 量化总结（用于对外说明这套流水线的实际效能）

| 指标 | 数据 |
|------|------|
| 产出 | 1 个可运行 App：19 个源文件 + 9 个测试文件、4 个页面、65 项测试 |
| 流水线资产 | 8 份契约模板 + 5 份 Agent 定义 + 1 份状态机 schema |
| 决策可溯性 | 18 条决策 100% 有记录（4 条用户拍板 / 14 条 Agent 定案） |
| 人工介入 | 5 个关卡 + 1 次 Figma 代执行（共 6 个触点） |
| 独立测试命中率 | 17 项 QA 用例发现 4 个开发自测未发现问题（≈24%） |
| 断点发现 | 15 条，其中 6 条属系统性缺陷 → 已全部转为改进项 |
| 工具故障 | 1 次（Figma MCP 令牌过期），被降级预案吸收，零阻塞 |
