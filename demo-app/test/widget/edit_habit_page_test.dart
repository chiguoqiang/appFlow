import 'package:demo_habit/models/habit_data.dart';
import 'package:demo_habit/pages/edit_habit_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  Finder saveButton() => find.widgetWithText(TextButton, '保存');

  bool saveEnabled(WidgetTester tester) =>
      tester.widget<TextButton>(saveButton()).onPressed != null;

  /// 表单较长，删除入口在底部，需滚动到可视区域。
  Future<void> scrollToDelete(WidgetTester tester) async {
    await tester.scrollUntilVisible(
      find.text('删除习惯'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
  }

  group('PG-02 习惯编辑', () {
    testWidgets('创建态：名称为空时保存禁用', (tester) async {
      await pumpPage(tester, const EditHabitPage());

      expect(find.text('新建习惯'), findsOneWidget);
      expect(saveEnabled(tester), isFalse);
    });

    testWidgets('输入合法名称后保存可用', (tester) async {
      await pumpPage(tester, const EditHabitPage());

      await tester.enterText(find.byType(TextField), '每天喝 8 杯水');
      await tester.pump();

      expect(saveEnabled(tester), isTrue);
    });

    testWidgets('名称为 21 字时提示错误且保存禁用', (tester) async {
      await pumpPage(tester, const EditHabitPage());

      await tester.enterText(find.byType(TextField), '一' * 21);
      await tester.pump();

      expect(find.text('名称需为 1-20 个字'), findsOneWidget);
      expect(saveEnabled(tester), isFalse);
    });

    testWidgets('名称 20 字为合法上限', (tester) async {
      await pumpPage(tester, const EditHabitPage());

      await tester.enterText(find.byType(TextField), '一' * 20);
      await tester.pump();

      expect(saveEnabled(tester), isTrue);
    });

    testWidgets('名称计数器显示当前字数', (tester) async {
      await pumpPage(tester, const EditHabitPage());

      await tester.enterText(find.byType(TextField), '阅读');
      await tester.pump();

      expect(find.text('2/20'), findsOneWidget);
    });

    testWidgets('切换每周 N 次后出现步进器，默认 3', (tester) async {
      await pumpPage(tester, const EditHabitPage());

      await tester.tap(find.text('每周 N 次'));
      await tester.pumpAndSettle();

      expect(find.text('3'), findsOneWidget);
    });

    testWidgets('步进器上限 7（到边界后加号禁用）', (tester) async {
      await pumpPage(tester, const EditHabitPage());

      await tester.tap(find.text('每周 N 次'));
      await tester.pumpAndSettle();

      final plus = find.widgetWithIcon(IconButton, Icons.add_circle_outline);
      for (var i = 0; i < 4; i++) {
        await tester.tap(plus);
        await tester.pump();
      }

      expect(find.text('7'), findsOneWidget);
      expect(
        tester.widget<IconButton>(plus).onPressed,
        isNull,
        reason: 'N=7 时加号应禁用',
      );
    });

    testWidgets('步进器下限 1（到边界后减号禁用）', (tester) async {
      await pumpPage(tester, const EditHabitPage());

      await tester.tap(find.text('每周 N 次'));
      await tester.pumpAndSettle();

      final minus = find.widgetWithIcon(
        IconButton,
        Icons.remove_circle_outline,
      );
      for (var i = 0; i < 2; i++) {
        await tester.tap(minus);
        await tester.pump();
      }

      expect(find.text('1'), findsOneWidget);
      expect(
        tester.widget<IconButton>(minus).onPressed,
        isNull,
        reason: 'N=1 时减号应禁用',
      );
    });

    testWidgets('保存新习惯后回到上一页且数据写入', (tester) async {
      await pumpPage(tester, const EditHabitPage());

      await tester.enterText(find.byType(TextField), '晨间冥想');
      await tester.pump();
      await tester.tap(saveButton());
      await tester.pumpAndSettle();

      // 页面已 pop（EditHabitPage 不再可见）
      expect(find.byType(EditHabitPage), findsNothing);
    });

    testWidgets('编辑态：标题为编辑习惯，展示删除入口', (tester) async {
      await pumpPage(
        tester,
        EditHabitPage(
          habit: makeHabit(id: 'h1', name: '喝水'),
        ),
        data: HabitData(
          habits: [makeHabit(id: 'h1', name: '喝水')],
          checkIns: [],
        ),
      );

      expect(find.text('编辑习惯'), findsOneWidget);
      await scrollToDelete(tester);
      expect(find.text('删除习惯'), findsOneWidget);
      expect(find.text('喝水'), findsOneWidget);
    });

    testWidgets('编辑态：删除需二次确认，确认后移除', (tester) async {
      await pumpPage(
        tester,
        EditHabitPage(
          habit: makeHabit(id: 'h1', name: '喝水'),
        ),
        data: HabitData(
          habits: [makeHabit(id: 'h1', name: '喝水')],
          checkIns: [makeCheckIn('h1', kToday)],
        ),
      );

      await scrollToDelete(tester);
      await tester.tap(find.text('删除习惯'));
      await tester.pumpAndSettle();

      expect(find.text('删除习惯？'), findsOneWidget);
      expect(find.textContaining('全部打卡记录'), findsOneWidget);

      await tester.tap(find.widgetWithText(TextButton, '删除'));
      await tester.pumpAndSettle();

      expect(find.byType(EditHabitPage), findsNothing);
    });

    testWidgets('删除对话框取消后不删除', (tester) async {
      await pumpPage(
        tester,
        EditHabitPage(
          habit: makeHabit(id: 'h1', name: '喝水'),
        ),
        data: HabitData(
          habits: [makeHabit(id: 'h1', name: '喝水')],
          checkIns: [],
        ),
      );

      await scrollToDelete(tester);
      await tester.tap(find.text('删除习惯'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TextButton, '取消'));
      await tester.pumpAndSettle();

      expect(find.byType(EditHabitPage), findsOneWidget);
      expect(find.text('编辑习惯'), findsOneWidget);
    });
  });
}
