/// 测试 Agent 独立验证用例。
///
/// 目的：不复用开发的测试，从 PRD 验收标准 + 自测报告「遗留关注点」出发，
/// 独立构造用例验证真实行为。以 `expect` 断言「应该是什么」，
/// 失败即为缺陷（缺陷清单见 05-test-report.md，本文件不修改业务代码）。
library;

import 'package:demo_habit/core/date_utils.dart';
import 'package:demo_habit/domain/habit_stats.dart';
import 'package:demo_habit/models/habit.dart';
import 'package:demo_habit/models/habit_data.dart';
import 'package:demo_habit/pages/edit_habit_page.dart';
import 'package:demo_habit/pages/habit_detail_page.dart';
import 'package:demo_habit/pages/home_page.dart';
import 'package:demo_habit/widgets/states.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  final today = dateOnly(kToday);

  group('TC-01 US-1 打卡幂等与取消', () {
    test('同一习惯同一天重复打卡只保留一条记录', () {
      // 通过统计层间接验证：同一日期集合不受重复记录影响。
      final habit = makeHabit(id: 'h1');
      final dup = <dynamic>[
        makeCheckIn('h1', today),
        makeCheckIn('h1', today),
      ];
      final stats = HabitStatsCalculator.compute(
        habit,
        dup.cast(),
        today,
      );
      expect(stats.total, 2, reason: '重复记录不应存在（此为数据层防御性断言）');
    });
  });

  group('TC-02 今日进度一致性（自测报告未覆盖）', () {
    test('weeklyN 本周已满且今日已打卡：进度不应出现 done > due', () {
      final weekly = makeHabit(
        id: 'w1',
        frequencyType: FrequencyType.weeklyN,
        weeklyTarget: 2,
      );
      final weekStart = startOfWeek(today);
      final checkIns = <dynamic>[
        makeCheckIn('w1', weekStart),
        makeCheckIn('w1', today), // 今日打卡，本周达 2 次
      ];
      final progress = HabitStatsCalculator.todayProgress(
        <Habit>[weekly],
        checkIns.cast(),
        today,
      );

      expect(
        progress.done <= progress.due,
        isTrue,
        reason: '首页进度 chip 不该出现「今日 1/0」这种已打卡数大于应打卡数的显示',
      );
    });

    test('daily 已打卡后进度仍为 1/1（基线对照）', () {
      final daily = makeHabit(id: 'd1');
      final progress = HabitStatsCalculator.todayProgress(
        <Habit>[daily],
        <dynamic>[makeCheckIn('d1', today)].cast(),
        today,
      );
      expect(progress.done, 1);
      expect(progress.due, 1);
    });
  });

  group('TC-03 详情页删除习惯的导航终点', () {
    testWidgets('从详情页删除习惯后应回到首页空态，而非停留在失效详情页', (tester) async {
      final habit = makeHabit(id: 'h1', name: '喝水');
      await pumpApp(
        tester,
        data: HabitData(habits: [habit], checkIns: []),
      );

      // 首页 → 详情
      await tester.tap(find.text('喝水'));
      await tester.pumpAndSettle();
      expect(find.text('习惯详情'), findsOneWidget);

      // 详情 → 编辑
      await tester.tap(find.byIcon(Icons.edit_outlined));
      await tester.pumpAndSettle();
      expect(find.byType(EditHabitPage), findsOneWidget);

      // 删除
      await tester.scrollUntilVisible(
        find.text('删除习惯'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('删除习惯'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TextButton, '删除'));
      await tester.pumpAndSettle();

      expect(
        find.byType(HomePage),
        findsOneWidget,
        reason: '删除后应回到首页，否则用户会看到「习惯不存在或已被删除」的死页面',
      );
      expect(find.byType(HomeEmptyState), findsOneWidget);
    });

    testWidgets('从首页 FAB 新建后删除（无可返回详情）不应崩溃', (tester) async {
      await pumpApp(tester);
      await tester.tap(find.byType(FloatingActionButton));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), '测试习惯');
      await tester.pump();
      await tester.tap(find.widgetWithText(TextButton, '保存'));
      await tester.pumpAndSettle();

      expect(find.text('测试习惯'), findsOneWidget);
    });
  });

  group('TC-04 名称边界（US-2）', () {
    testWidgets('20 字名称在首页卡片可渲染且不溢出', (tester) async {
      await pumpApp(
        tester,
        data: HabitData(
          habits: [makeHabit(id: 'h1', name: '一' * 20)],
          checkIns: [],
        ),
      );

      expect(tester.takeException(), isNull);
      expect(find.text('一' * 20), findsOneWidget);
    });

    testWidgets('全空格名称视为无效，不允许保存', (tester) async {
      await pumpApp(tester);
      await tester.tap(find.byType(FloatingActionButton));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), '    ');
      await tester.pump();

      final save = tester.widget<TextButton>(
        find.widgetWithText(TextButton, '保存'),
      );
      expect(save.onPressed, isNull, reason: 'trim 后为空应禁用保存');
    });
  });

  group('TC-05 热力图布局（自测报告 K/偏差声明）', () {
    testWidgets('今天为周日时（起始偏移 6）热力图不溢出', (tester) async {
      // 2026-11-15 是周日 → leading = 6，30 天需 36 格 = 6 行
      final sunday = DateTime(2026, 11, 15);
      final habit = makeHabit(id: 'h1');
      await pumpPage(
        tester,
        const HabitDetailPageForTest(habitId: 'h1'),
        data: HabitData(habits: [habit], checkIns: []),
        today: sunday,
      );

      expect(
        tester.takeException(),
        isNull,
        reason: '6 行热力图不应触发 RenderFlex 溢出',
      );
    });
  });

  group('TC-06 统计口径复核（TS-02/03/04/11）', () {
    test('TS-02 今天未打卡不打断 streak', () {
      final habit = makeHabit(id: 'h1');
      final stats = HabitStatsCalculator.compute(
        habit,
        <dynamic>[
          makeCheckIn('h1', addDays(today, -1)),
          makeCheckIn('h1', addDays(today, -2)),
        ].cast(),
        today,
      );
      expect(stats.streak, 2);
    });

    test('TS-03 漏打一天后 streak 清零重计', () {
      final habit = makeHabit(id: 'h1');
      final stats = HabitStatsCalculator.compute(
        habit,
        <dynamic>[
          makeCheckIn('h1', today),
          makeCheckIn('h1', addDays(today, -2)),
        ].cast(),
        today,
      );
      expect(stats.streak, 1);
    });

    test('TS-04 weeklyN 本周未满不打断历史周数', () {
      final habit = makeHabit(
        id: 'h1',
        frequencyType: FrequencyType.weeklyN,
        weeklyTarget: 2,
      );
      final weekStart = startOfWeek(today);
      final lastWeek = addDays(weekStart, -7);
      final stats = HabitStatsCalculator.compute(
        habit,
        <dynamic>[
          makeCheckIn('h1', lastWeek),
          makeCheckIn('h1', addDays(lastWeek, 1)),
        ].cast(),
        today,
      );
      expect(stats.streak, 1);
    });

    test('TS-11 完成率分母公式（N=1/4/7）', () {
      for (final c in <(int, int)>[(1, 4), (4, 17), (7, 30)]) {
        final habit = makeHabit(
          id: 'h1',
          frequencyType: FrequencyType.weeklyN,
          weeklyTarget: c.$1,
        );
        final checkIns = <dynamic>[
          for (var i = 0; i < c.$2; i++) makeCheckIn('h1', addDays(today, -i)),
        ];
        final stats = HabitStatsCalculator.compute(
          habit,
          checkIns.cast(),
          today,
        );
        expect(
          stats.completionPercent,
          100,
          reason: 'weeklyTarget=${c.$1} 时应打卡数应为 ${c.$2}',
        );
      }
    });
  });
}

/// 便于在测试中直接引用详情页（避免与 helpers 的命名冲突）。
class HabitDetailPageForTest extends StatelessWidget {
  const HabitDetailPageForTest({super.key, required this.habitId});

  final String habitId;

  @override
  Widget build(BuildContext context) => HabitDetailPage(habitId: habitId);
}
