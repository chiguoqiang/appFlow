import 'package:flutter/material.dart';

import '../models/habit.dart';
import '../theme/app_theme.dart';
import '../theme/habit_presets.dart';

/// 首页习惯卡片。
class HabitCard extends StatelessWidget {
  const HabitCard({
    super.key,
    required this.habit,
    required this.checked,
    required this.onToggle,
    required this.onTap,
  });

  final Habit habit;
  final bool checked;
  final VoidCallback onToggle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = colorFor(habit.colorKey);

    return Opacity(
      opacity: checked ? AppShape.checkedCardOpacity : 1,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(minHeight: 72),
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.s + AppSpacing.xs,
            vertical: AppSpacing.s + AppSpacing.xs,
          ),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(AppRadius.card),
            boxShadow: AppShape.cardShadow,
          ),
          child: Row(
            children: <Widget>[
              // 图标：40pt 圆形 + 习惯色 20% 底
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: AppShape.habitIconBgOpacity),
                  shape: BoxShape.circle,
                ),
                child: Icon(iconFor(habit.iconKey), size: 20, color: color),
              ),
              const SizedBox(width: AppSpacing.s + AppSpacing.xs),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Text(
                      habit.name,
                      style: AppType.titleMedium,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    Text(frequencyLabel(habit), style: AppType.label),
                  ],
                ),
              ),
              _CheckButton(color: color, checked: checked, onTap: onToggle),
            ],
          ),
        ),
      ),
    );
  }
}

/// 频率文案。
String frequencyLabel(Habit habit) {
  return habit.frequencyType == FrequencyType.daily
      ? '每天'
      : '每周 ${habit.weeklyTarget} 次';
}

/// 44pt 圆形打卡按钮。
class _CheckButton extends StatelessWidget {
  const _CheckButton({
    required this.color,
    required this.checked,
    required this.onTap,
  });

  final Color color;
  final bool checked;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: checked ? '取消打卡' : '打卡',
      child: Tooltip(
        message: checked ? '取消打卡' : '打卡',
        child: InkResponse(
          onTap: onTap,
          radius: AppShape.touchTargetMin / 2,
          child: Container(
            width: AppShape.touchTargetMin,
            height: AppShape.touchTargetMin,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: checked ? color : Colors.transparent,
              border: checked ? null : Border.all(color: color, width: 2),
            ),
            child: Icon(
              Icons.check,
              size: 20,
              color: checked ? AppColors.surface : color,
            ),
          ),
        ),
      ),
    );
  }
}
