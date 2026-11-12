import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/date_utils.dart';
import '../domain/habit_stats.dart';
import '../models/habit.dart';
import '../models/habit_data.dart';
import '../providers/habit_provider.dart';
import '../theme/app_theme.dart';
import '../widgets/habit_card.dart';
import '../widgets/states.dart';
import 'edit_habit_page.dart';
import 'habit_detail_page.dart';
import 'settings_page.dart';

/// PG-01 今日打卡（首页）。
class HomePage extends ConsumerWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final today = dateOnly(ref.watch(clockProvider)());
    final asyncData = ref.watch(habitControllerProvider);

    return Scaffold(
      body: SafeArea(
        child: asyncData.when(
          loading: () => const _HomeSkeleton(),
          error: (error, _) => ErrorState(
            message: '数据加载失败',
            onRetry: () => ref.invalidate(habitControllerProvider),
          ),
          data: (data) => _HomeContent(data: data, today: today),
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _openCreate(context),
        backgroundColor: AppColors.primary,
        foregroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.card),
        ),
        tooltip: '新建习惯',
        child: const Icon(Icons.add),
      ),
    );
  }

  static void _openCreate(BuildContext context) {
    Navigator.of(
      context,
    ).push(MaterialPageRoute<void>(builder: (_) => const EditHabitPage()));
  }
}

class _HomeContent extends ConsumerWidget {
  const _HomeContent({required this.data, required this.today});

  final HabitData data;
  final DateTime today;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final progress = HabitStatsCalculator.todayProgress(
      data.habits,
      data.checkIns,
      today,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.m,
            AppSpacing.s,
            AppSpacing.m,
            0,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      formatHeaderDate(today),
                      style: AppType.display,
                    ),
                  ),
                  IconButton(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => const SettingsPage(),
                      ),
                    ),
                    tooltip: '设置',
                    icon: const Icon(
                      Icons.settings_outlined,
                      size: 24,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.s),
              _ProgressChip(done: progress.done, due: progress.due),
              const SizedBox(height: AppSpacing.m),
            ],
          ),
        ),
        Expanded(
          child: data.habits.isEmpty
              ? HomeEmptyState(onCreate: () => HomePage._openCreate(context))
              : ListView.separated(
                  padding: const EdgeInsets.fromLTRB(
                    AppSpacing.m,
                    0,
                    AppSpacing.m,
                    AppSpacing.l * 2,
                  ),
                  itemCount: data.habits.length,
                  separatorBuilder: (_, _) =>
                      const SizedBox(height: AppSpacing.s),
                  itemBuilder: (context, index) {
                    final habit = data.habits[index];
                    return HabitCard(
                      habit: habit,
                      checked: HabitStatsCalculator.isCheckedToday(
                        habit.id,
                        data.checkIns,
                        today,
                      ),
                      onToggle: () => ref
                          .read(habitControllerProvider.notifier)
                          .toggleToday(habit.id),
                      onTap: () => _openDetail(context, habit),
                    );
                  },
                ),
        ),
      ],
    );
  }

  void _openDetail(BuildContext context, Habit habit) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => HabitDetailPage(habitId: habit.id),
      ),
    );
  }
}

class _ProgressChip extends StatelessWidget {
  const _ProgressChip({required this.done, required this.due});

  final int done;
  final int due;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.s + AppSpacing.xs,
        vertical: 6,
      ),
      decoration: BoxDecoration(
        color: AppColors.primarySoft,
        borderRadius: BorderRadius.circular(AppRadius.chip),
      ),
      child: Text(
        '今日 $done/$due',
        style: AppType.label.copyWith(color: AppColors.primary),
      ),
    );
  }
}

class _HomeSkeleton extends StatelessWidget {
  const _HomeSkeleton();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.m),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: const <Widget>[
          SizedBox(height: AppSpacing.s),
          SkeletonCard(),
          SizedBox(height: AppSpacing.s),
          SkeletonCard(),
          SizedBox(height: AppSpacing.s),
          SkeletonCard(),
        ],
      ),
    );
  }
}
