import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/date_utils.dart';
import '../domain/habit_stats.dart';
import '../models/habit.dart';
import '../providers/habit_provider.dart';
import '../theme/app_theme.dart';
import '../theme/habit_presets.dart';
import '../widgets/app_card.dart';
import '../widgets/habit_card.dart' show frequencyLabel;
import '../widgets/habit_heatmap.dart';
import '../widgets/states.dart';
import 'edit_habit_page.dart';

/// PG-03 习惯详情。
class HabitDetailPage extends ConsumerWidget {
  const HabitDetailPage({super.key, required this.habitId});

  final String habitId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncData = ref.watch(habitControllerProvider);
    final today = dateOnly(ref.watch(clockProvider)());

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: const Text('习惯详情'),
        actions: <Widget>[
          IconButton(
            tooltip: '编辑',
            icon: const Icon(Icons.edit_outlined),
            onPressed: () => _openEdit(context, ref),
          ),
          const SizedBox(width: AppSpacing.s),
        ],
      ),
      body: asyncData.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => ErrorState(
          message: '数据加载失败',
          onRetry: () => ref.invalidate(habitControllerProvider),
        ),
        data: (data) {
          Habit? habit;
          for (final h in data.habits) {
            if (h.id == habitId) {
              habit = h;
              break;
            }
          }
          if (habit == null) {
            return const ErrorState(message: '习惯不存在或已被删除');
          }
          return _DetailContent(habit: habit, today: today);
        },
      ),
    );
  }

  void _openEdit(BuildContext context, WidgetRef ref) {
    final data = ref.read(habitControllerProvider).value;
    if (data == null) return;
    for (final h in data.habits) {
      if (h.id == habitId) {
        Navigator.of(context).push(
          MaterialPageRoute<void>(builder: (_) => EditHabitPage(habit: h)),
        );
        return;
      }
    }
  }
}

class _DetailContent extends ConsumerWidget {
  const _DetailContent({required this.habit, required this.today});

  final Habit habit;
  final DateTime today;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(habitControllerProvider).value;
    final checkIns = data?.checkIns ?? const [];
    final stats = HabitStatsCalculator.compute(habit, checkIns, today);
    final color = colorFor(habit.colorKey);
    final checkedKeys = <String>{
      for (final c in checkIns)
        if (c.habitId == habit.id) c.date,
    };

    return ListView(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.m,
        AppSpacing.s,
        AppSpacing.m,
        AppSpacing.l,
      ),
      children: <Widget>[
        // 习惯头
        Row(
          children: <Widget>[
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: color.withValues(alpha: AppShape.habitIconBgOpacity),
                shape: BoxShape.circle,
              ),
              child: Icon(iconFor(habit.iconKey), size: 30, color: color),
            ),
            const SizedBox(width: AppSpacing.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    habit.name,
                    style: AppType.titleLarge,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(frequencyLabel(habit), style: AppType.label),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.l),

        // 统计三格
        AppCard(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.m),
          child: IntrinsicHeight(
            child: Row(
              children: <Widget>[
                _StatCell(
                  statId: 'streak',
                  value: '${stats.streak}',
                  label: '🔥 连续天数',
                ),
                const VerticalDivider(),
                _StatCell(
                  statId: 'total',
                  value: '${stats.total}',
                  label: '总打卡',
                ),
                const VerticalDivider(),
                _StatCell(
                  statId: 'rate',
                  value: '${stats.completionPercent}%',
                  label: '30天完成率',
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.m),

        // 热力图
        AppCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('近 30 天', style: AppType.titleMedium),
              const SizedBox(height: AppSpacing.m),
              HabitHeatmap(
                today: today,
                checkedDateKeys: checkedKeys,
                color: color,
              ),
              if (stats.total == 0) ...<Widget>[
                const SizedBox(height: AppSpacing.m),
                Center(
                  child: Text(
                    '完成第一次打卡吧 👇',
                    style: AppType.body.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _StatCell extends StatelessWidget {
  const _StatCell({
    required this.statId,
    required this.value,
    required this.label,
  });

  final String statId;
  final String value;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          Text(
            value,
            key: ValueKey<String>('stat-$statId'),
            style: AppType.display,
          ),
          const SizedBox(height: 2),
          Text(label, style: AppType.label, textAlign: TextAlign.center),
        ],
      ),
    );
  }
}
