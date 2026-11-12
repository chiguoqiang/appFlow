import 'package:demo_habit/core/date_utils.dart';
import 'package:demo_habit/models/habit_data.dart';
import 'package:demo_habit/pages/habit_detail_page.dart';
import 'package:demo_habit/widgets/habit_heatmap.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  /// 统计 30 格热力图格子数量。
  int heatCellCount(WidgetTester tester) {
    return tester
        .widgetList(
          find.byWidgetPredicate(
            (widget) =>
                widget.key is ValueKey<String> &&
                (widget.key! as ValueKey<String>).value.startsWith(
                  'heat-cell-',
                ),
          ),
        )
        .length;
  }

  group('PG-03 习惯详情', () {
    /// 读取统计值文本。
    String statValue(WidgetTester tester, String statId) {
      final widget = tester.widget<Text>(
        find.byKey(ValueKey<String>('stat-$statId')),
      );
      return widget.data ?? '';
    }

    testWidgets('展示习惯标识与频率', (tester) async {
      final habit = makeHabit(id: 'h1', name: '喝水');
      await pumpPage(
        tester,
        const HabitDetailPage(habitId: 'h1'),
        data: HabitData(habits: [habit], checkIns: []),
      );

      expect(find.text('习惯详情'), findsOneWidget);
      expect(find.text('喝水'), findsOneWidget);
      expect(find.text('每天'), findsOneWidget);
    });

    testWidgets('无打卡时统计为 0 且展示引导文案', (tester) async {
      final habit = makeHabit(id: 'h1');
      await pumpPage(
        tester,
        const HabitDetailPage(habitId: 'h1'),
        data: HabitData(habits: [habit], checkIns: []),
      );

      expect(statValue(tester, 'streak'), '0');
      expect(statValue(tester, 'total'), '0');
      expect(statValue(tester, 'rate'), '0%');
      expect(find.text('完成第一次打卡吧 👇'), findsOneWidget);
    });

    testWidgets('有打卡时展示连续天数/总打卡/完成率', (tester) async {
      final habit = makeHabit(id: 'h1');
      final checkIns = [
        makeCheckIn('h1', kToday),
        makeCheckIn('h1', addDays(kToday, -1)),
      ];
      await pumpPage(
        tester,
        const HabitDetailPage(habitId: 'h1'),
        data: HabitData(habits: [habit], checkIns: checkIns),
      );

      expect(statValue(tester, 'streak'), '2');
      expect(statValue(tester, 'total'), '2');
      expect(statValue(tester, 'rate'), '7%'); // 2/30 ≈ 6.67 → 7%
      expect(find.text('完成第一次打卡吧 👇'), findsNothing);
    });

    testWidgets('热力图恰有 30 个日期格子且包含今天', (tester) async {
      final habit = makeHabit(id: 'h1');
      await pumpPage(
        tester,
        const HabitDetailPage(habitId: 'h1'),
        data: HabitData(habits: [habit], checkIns: []),
      );

      expect(heatCellCount(tester), 30);
      expect(
        find.byKey(ValueKey<String>('heat-cell-${formatDateKey(kToday)}')),
        findsOneWidget,
      );
      // 最早一格 = 今天 - 29 天
      expect(
        find.byKey(
          ValueKey<String>('heat-cell-${formatDateKey(addDays(kToday, -29))}'),
        ),
        findsOneWidget,
      );
    });

    testWidgets('习惯不存在时展示提示', (tester) async {
      await pumpPage(
        tester,
        const HabitDetailPage(habitId: 'missing'),
        data: HabitData.empty,
      );

      expect(find.text('习惯不存在或已被删除'), findsOneWidget);
    });

    testWidgets('点击编辑进入编辑页', (tester) async {
      final habit = makeHabit(id: 'h1', name: '喝水');
      await pumpPage(
        tester,
        const HabitDetailPage(habitId: 'h1'),
        data: HabitData(habits: [habit], checkIns: []),
      );

      await tester.tap(find.byIcon(Icons.edit_outlined));
      await tester.pumpAndSettle();

      expect(find.text('编辑习惯'), findsOneWidget);
    });

    testWidgets('热力图组件可独立渲染指定天数', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: HabitHeatmap(
              today: kToday,
              checkedDateKeys: {formatDateKey(kToday)},
              color: const Color(0xFF4F6BED),
              days: 7,
            ),
          ),
        ),
      );

      expect(find.byType(HabitHeatmap), findsOneWidget);
      expect(
        find.byKey(ValueKey<String>('heat-cell-${formatDateKey(kToday)}')),
        findsOneWidget,
      );
    });
  });
}
