#!/usr/bin/env bash
# 规范体系装配（P0 最大断点的修复）
#
# 背景：P0 中简报硬约束「遵循 flutter-dev-playbook / AGENTS.md 三级 Rules」实际未达成——
# Agent 定义里声明了依赖，但没有任何环节把 rules 装到项目里。本脚本就是那个环节。
#
# 用法：sync-spec.sh <project_dir>
#   sync-spec.sh demo-app
#
# 幂等：重复执行不会重复追加 AGENTS.md 索引；rules 版本变化时才覆盖。

set -euo pipefail

PROJECT_DIR="${1:-}"
if [[ -z "$PROJECT_DIR" ]]; then
  echo "用法: $0 <project_dir>" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET="$REPO_ROOT/$PROJECT_DIR"

if [[ ! -d "$TARGET" ]]; then
  echo "✗ 项目目录不存在: $TARGET" >&2
  exit 1
fi

# 规范源：优先项目级，其次个人级
CANDIDATES=(
  "$REPO_ROOT/.github/skills/flutter-dev-playbook/rules"
  "$HOME/.agents/skills/flutter-dev-playbook/rules"
  "$HOME/.claude/skills/flutter-dev-playbook/rules"
)

SPEC_SRC=""
for c in "${CANDIDATES[@]}"; do
  if [[ -d "$c" ]]; then SPEC_SRC="$c"; break; fi
done

if [[ -z "$SPEC_SRC" ]]; then
  echo "✗ 未找到 flutter-dev-playbook/rules（尝试过：）" >&2
  printf '   - %s\n' "${CANDIDATES[@]}" >&2
  echo "  请先安装该 skill，或手动放入项目。" >&2
  exit 3
fi

DEST="$TARGET/.github/skills/flutter-dev-playbook/rules"
mkdir -p "$(dirname "$DEST")"

if [[ -d "$DEST" ]] && diff -rq "$SPEC_SRC" "$DEST" >/dev/null 2>&1; then
  echo "· rules 已是最新（跳过复制）: ${DEST#$REPO_ROOT/}"
else
  rm -rf "$DEST"
  cp -R "$SPEC_SRC" "$DEST"
  echo "✓ 已装配 rules: ${SPEC_SRC} → ${DEST#$REPO_ROOT/}"
fi

# 生成/更新根 AGENTS.md 索引（幂等：有标记则不重复写）
AGENTS="$TARGET/AGENTS.md"
MARKER="<!-- flutter-dev-playbook:index -->"

if [[ -f "$AGENTS" ]] && grep -q "$MARKER" "$AGENTS"; then
  echo "· AGENTS.md 索引已存在（跳过）: ${AGENTS#$REPO_ROOT/}"
else
  {
    [[ -f "$AGENTS" ]] && echo "" && echo "---" && echo ""
    echo "$MARKER"
    echo "# 规范索引（由 sync-spec.sh 生成，勿手改本节）"
    echo ""
    echo "规范优先级：\`docs/rules/*.md\` > \`libs/<库名>.md\` > \`L*.md\`"
    echo ""
    echo "## 入口"
    echo ""
    echo "- 完整流程总纲：\`.github/skills/flutter-dev-playbook/rules/WORKFLOW.md\`"
    echo ""
    echo "## 场景路由"
    echo ""
    echo "| 场景 | 执行文件 |"
    echo "|------|---------|"
    if [[ -d "$DEST/flutter" ]]; then
      for f in "$DEST"/flutter/PLAYBOOK-*.md; do
        [[ -e "$f" ]] || continue
        name="$(basename "$f")"
        scene="${name#PLAYBOOK-}"
        scene="${scene%.md}"
        scene="${scene//-/ }"
        echo "| $scene | \`$name\` |"
      done
    fi
    echo ""
    echo "## 红线（摘要）"
    echo ""
    echo "- 生成文件禁改、原生工程只读、禁擅自加依赖、禁真实密钥、禁 \`!\` 强解"
    echo "- 业务歧义不猜：记「待确认」，保守默认推进，汇报时逐条标注"
    echo "- 每场景 DoD：\`flutter analyze\` 零 error + \`flutter test\` 全绿 + format + 红线自查"
  } >> "$AGENTS"
  echo "✓ 已生成 AGENTS.md 索引: ${AGENTS#$REPO_ROOT/}"
fi

echo ""
echo "完成。验证："
echo "  test -f $PROJECT_DIR/AGENTS.md && test -d $PROJECT_DIR/.github/skills/flutter-dev-playbook/rules && echo OK"
