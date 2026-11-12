import 'package:demo_habit/models/habit.dart';
import 'package:demo_habit/models/habit_data.dart';
import 'package:demo_habit/widgets/habit_card.dart';
import 'package:demo_habit/widgets/states.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  group('PG-01 今日打卡', () {
    testWidgets('无习惯时展示空态引导', (tester) async {
      await pumpApp(tester);

      expect(find.byType(HomeEmptyState), findsOneWidget);
      expect(find.text('还没有习惯'), findsOneWidget);
      expect(find.text('＋ 创建习惯'), findsOneWidget);
    });

    testWidgets('展示日期头部与今日进度 chip', (tester) async {
      await pumpApp(
        tester,
        data: HabitData(
          habits: [makeHabit(id: 'h1')],
          checkIns: [],
        ),
      );

      expect(find.textContaining('11月11日'), findsOneWidget);
      expect(find.text('今日 0/1'), findsOneWidget);
      expect(find.byType(HabitCard), findsOneWidget);
      expect(find.text('喝水'), findsOneWidget);
      expect(find.text('每天'), findsOneWidget);
    });

    testWidgets('点击打卡按钮后切换为已打卡态且进度更新', (tester) async {
      await pumpApp(
        tester,
        data: HabitData(
          habits: [makeHabit(id: 'h1')],
          checkIns: [],
        ),
      );

      await tester.tap(find.byTooltip('打卡'));
      await tester.pumpAndSettle();

      expect(find.text('今日 1/1'), findsOneWidget);
      // 已打卡后按钮语义变为「取消打卡」
      expect(find.byTooltip('取消打卡'), findsOneWidget);
    });

    testWidgets('取消打卡回到未打卡态', (tester) async {
      await pumpApp(
        tester,
        data: HabitData(
          habits: [makeHabit(id: 'h1')],
          checkIns: [makeCheckIn('h1', kToday)],
        ),
      );

      expect(find.text('今日 1/1'), findsOneWidget);
      await tester.tap(find.byTooltip('取消打卡'));
      await tester.pumpAndSettle();

      expect(find.text('今日 0/1'), findsOneWidget);
    });

    testWidgets('每周型习惯展示频率文案', (tester) async {
      await pumpApp(
        tester,
        data: HabitData(
          habits: [
            makeHabit(
              id: 'h1',
              frequencyType: FrequencyType.weeklyN,
              weeklyTarget: 3,
            ),
          ],
          checkIns: [],
        ),
      );

      expect(find.text('每周 3 次'), findsOneWidget);
    });

    testWidgets('多习惯按创建顺序渲染', (tester) async {
      await pumpApp(
        tester,
        data: HabitData(
          habits: [
            makeHabit(id: 'h1', name: '喝水'),
            makeHabit(id: 'h2', name: '阅读'),
            makeHabit(id: 'h3', name: '跑步'),
          ],
          checkIns: [],
        ),
      );

      expect(find.byType(HabitCard), findsNWidgets(3));
      final cards = tester.widgetList<HabitCard>(find.byType(HabitCard));
      expect(cards.map((c) => c.habit.id), ['h1', 'h2', 'h3']);
    });

    testWidgets('点击 FAB 打开新建页', (tester) async {
      await pumpApp(tester);

      await tester.tap(find.byType(FloatingActionButton));
      await tester.pumpAndSettle();

      expect(find.text('新建习惯'), findsOneWidget);
    });

    testWidgets('点击卡片进入详情页', (tester) async {
      await pumpApp(
        tester,
        data: HabitData(
          habits: [makeHabit(id: 'h1')],
          checkIns: [],
        ),
      );

      await tester.tap(find.text('喝水'));
      await tester.pumpAndSettle();

      expect(find.text('习惯详情'), findsOneWidget);
      expect(find.text('近 30 天'), findsOneWidget);
    });

    testWidgets('点击设置进入设置页', (tester) async {
      await pumpApp(tester);

      await tester.tap(find.byIcon(Icons.settings_outlined));
      await tester.pumpAndSettle();

      expect(find.text('设置'), findsOneWidget);
      expect(find.text('重置所有数据'), findsOneWidget);
    });
  });
}
