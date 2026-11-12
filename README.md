# AI 移动应用生产线（AI App Pipeline）

> **输入一个想法，产出一个可运行的 App。**
> 采用「Workflow 骨架 + Agent 节点 + 人工关卡」：流程写成可版本化的 YAML 契约，
> 由调度器强制执行；Agent 只是 SOP 里的一个动作。

**当前状态**：P0 完成 · M1 完成 · **M2 完成**（调度器可端到端跑通）

---

## 👉 新接手先读这里

**[`docs/HANDOFF.md`](docs/HANDOFF.md)** —— 换机/换人的唯一入口：
环境重建、进度快照、目录导航、常用命令、架构决策、已踩的坑、下一步。

---

## 这是什么

传统做法是「人写需求 → 人设计方案 → 人写代码 → 人测试」。这套系统把它变成：

```
输入想法  →  规划 → 设计 → 开发 → 测试 → 验收  →  可运行的 App
            ↑      ↑      ↑      ↑      ↑
          人工关卡（三态：通过 / 调整 / 打回）
```

**五阶段流程**，每阶段：
- 由 SOP（YAML）定义步骤与校验点
- 由 Agent 执行主体工作
- 由 manifest + 规则引擎机械校验交付物
- **必然停在人工关卡**，等人做三态决策

**两条流程**：
- **新项目**：从零建 App（6 阶段）
- **新需求**：改现有 App（6 阶段，增量轻量流程）

---

## 核心资产

| 目录 | 内容 | 说明 |
|------|------|------|
| `pipeline/sops/` | **13 个 SOP** | 流程的唯一权威来源 |
| `pipeline/manifests/` | **14 份校验规则** | 交付物字段机械校验 |
| `pipeline/gates/` | **4 套规则集 / 36 条规则** | 质量门 + DoD + 资产探测 + 内容规则 |
| `pipeline/agents/` | **5 份执行契约** | 职责边界 + 红线 + gate 响应 |
| `pipeline/templates/` | **7 份交付物模板** | 含 P0 教训硬化 |
| `pipeline/cli/` | **调度器（Python）** | M2 内核 + 本地可视化台 |
| `demo-app/` | **产出示例** | 习惯打卡 App（Flutter，65 项测试全绿） |

---

## 快速验证（3 条命令）

```bash
# 0. 用可视化台（最直观）
cd pipeline/cli && export PATH="$PWD:$PATH" && pipeline serve --open

# 1. 契约自检（应：通过 31 | 警告 0 | 错误 0）
python3 pipeline/scripts/validate-contracts.py

# 2. 调度器测试（应全绿）
cd pipeline/cli && uv venv --python python3.12 .venv \
  && uv pip install --python .venv/bin/python typer pydantic pyyaml pytest \
  && PYTHONPATH=src ./.venv/bin/python -m pytest tests/ -q

# 3. 产品测试（应：All tests passed!）
cd ../../demo-app && flutter test
```

---

## 设计原则

1. **每阶段必停** —— 人工关卡是硬约束，不做「一键连跑到验收」
2. **动作类型封闭** —— SOP 只认 7 种动作，越少越可预测
3. **规则即数据** —— 校验规则写在 YAML，不写进 prompt；可 diff、可机器执行
4. **未实现必须 `skip`，绝不静默 `pass`** —— 静默通过与不校验等价，且更危险
5. **降级必须登记回填** —— P0 血泪教训：降级即遗忘
6. **决策全程可溯** —— 每个取舍都写进 Decision Log，没有「未记录的口头决定」

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | **交接入口**（先读这个） |
| [`docs/runbook.md`](docs/runbook.md) | P0 断点日志（15 条）+ 复盘结论 |
| [`docs/m1-walkthrough.md`](docs/m1-walkthrough.md) | M1 验收：15 条断点 → 机器拦截对照表 |
| [`docs/p1-backlog.md`](docs/p1-backlog.md) | 缺陷与改进项清单 |
| [`pipeline/sops/_actions.md`](pipeline/sops/_actions.md) | 7 种动作类型参考 |
| [`pipeline/manifests/README.md`](pipeline/manifests/README.md) | manifest 格式规范 |

---

## 已知限制

- Figma 写入通道不可用（AI 不直接画布绘制，设计生成需人工代执行）
- UI 快照自动化缺失（需 `integration_test`，M3/M4 待补）
- headless Agent 未接入（当前用 MockAgent 验证骨架，M3 接入）
- preflight 的 Figma/组件库探测未实现（M3）
- 仅支持 Flutter（iOS/Android）；不支持 Web / 后端服务
