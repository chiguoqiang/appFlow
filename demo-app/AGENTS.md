
---

<!-- flutter-dev-playbook:index -->
# 规范索引（由 sync-spec.sh 生成，勿手改本节）

规范优先级：`docs/rules/*.md` > `libs/<库名>.md` > `L*.md`

## 入口

- 完整流程总纲：`.github/skills/flutter-dev-playbook/rules/WORKFLOW.md`

## 场景路由

| 场景 | 执行文件 |
|------|---------|
| ARCHITECTURE | `PLAYBOOK-ARCHITECTURE.md` |
| BIZ LOGIC | `PLAYBOOK-BIZ-LOGIC.md` |
| NEW API | `PLAYBOOK-NEW-API.md` |
| NEW FEATURE | `PLAYBOOK-NEW-FEATURE.md` |
| NEW PROJECT | `PLAYBOOK-NEW-PROJECT.md` |
| UI PAGE | `PLAYBOOK-UI-PAGE.md` |

## 红线（摘要）

- 生成文件禁改、原生工程只读、禁擅自加依赖、禁真实密钥、禁 `!` 强解
- 业务歧义不猜：记「待确认」，保守默认推进，汇报时逐条标注
- 每场景 DoD：`flutter analyze` 零 error + `flutter test` 全绿 + format + 红线自查
