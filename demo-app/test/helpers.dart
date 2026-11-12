import 'package:demo_habit/app.dart';
import 'package:demo_habit/data/habit_repository.dart';
import 'package:demo_habit/models/check_in.dart';
import 'package:demo_habit/models/habit.dart';
import 'package:demo_habit/models/habit_data.dart';
import 'package:demo_habit/providers/habit_provider.dart';
import 'package:demo_habit/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// 测试基准日（所有用例统一，避免依赖系统时间）。
final DateTime kToday = DateTime(2026, 11, 11, 9, 30);

/// 构造习惯。
Habit makeHabit({
  required String id,
  String name = '喝水',
  FrequencyType frequencyType = FrequencyType.daily,
  int weeklyTarget = 3,
  DateTime? createdAt,
}) {
  return Habit(
    id: id,
    name: name,
    iconKey: 'water',
    colorKey: 'blue',
    frequencyType: frequencyType,
    weeklyTarget: weeklyTarget,
    createdAt: createdAt ?? DateTime(2026, 1, 1),
  );
}

/// 构造打卡记录。
CheckIn makeCheckIn(String habitId, DateTime date) {
  final key =
      '${date.year.toString().padLeft(4, '0')}-'
      '${date.month.toString().padLeft(2, '0')}-'
      '${date.day.toString().padLeft(2, '0')}';
  return CheckIn(
    id: '$habitId-$key',
    habitId: habitId,
    date: key,
    createdAt: date,
  );
}

/// 启动完整 App（首页）。
Future<void> pumpApp(
  WidgetTester tester, {
  HabitData data = HabitData.empty,
  DateTime? today,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        habitRepositoryProvider.overrideWithValue(
          InMemoryHabitRepository(data),
        ),
        clockProvider.overrideWithValue(() => today ?? kToday),
      ],
      child: const DemoHabitApp(),
    ),
  );
  await tester.pumpAndSettle();
}

/// 启动单个页面（详情/编辑/设置等）。
Future<void> pumpPage(
  WidgetTester tester,
  Widget page, {
  HabitData data = HabitData.empty,
  DateTime? today,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        habitRepositoryProvider.overrideWithValue(
          InMemoryHabitRepository(data),
        ),
        clockProvider.overrideWithValue(() => today ?? kToday),
      ],
      child: MaterialApp(theme: buildAppTheme(), home: page),
    ),
  );
  await tester.pumpAndSettle();
}
