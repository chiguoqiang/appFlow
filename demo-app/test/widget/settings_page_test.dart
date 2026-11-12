import 'package:demo_habit/models/habit_data.dart';
import 'package:demo_habit/pages/settings_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  group('PG-04 设置', () {
    testWidgets('展示数据分组与版本信息', (tester) async {
      await pumpPage(tester, const SettingsPage());

      expect(find.text('设置'), findsOneWidget);
      expect(find.text('重置所有数据'), findsOneWidget);
      expect(find.text('版本'), findsOneWidget);
      expect(find.text('1.0.0'), findsOneWidget);
    });

    testWidgets('重置需二次确认：取消不生效', (tester) async {
      await pumpPage(tester, const SettingsPage());

      await tester.tap(find.text('重置所有数据'));
      await tester.pumpAndSettle();

      expect(find.text('重置所有数据？'), findsOneWidget);
      expect(find.textContaining('此操作不可恢复'), findsOneWidget);

      await tester.tap(find.widgetWithText(TextButton, '取消'));
      await tester.pumpAndSettle();

      expect(find.byType(SettingsPage), findsOneWidget);
    });

    testWidgets('重置确认后返回并清空数据（首页回到空态）', (tester) async {
      await pumpApp(
        tester,
        data: HabitData(
          habits: [makeHabit(id: 'h1', name: '喝水')],
          checkIns: [makeCheckIn('h1', kToday)],
        ),
      );

      // 进入设置
      await tester.tap(find.byIcon(Icons.settings_outlined));
      await tester.pumpAndSettle();
      expect(find.text('重置所有数据'), findsOneWidget);

      // 执行重置
      await tester.tap(find.text('重置所有数据'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TextButton, '重置'));
      await tester.pumpAndSettle();

      // 已返回首页且为空态
      expect(find.byType(SettingsPage), findsNothing);
      expect(find.text('还没有习惯'), findsOneWidget);
    });
  });
}
