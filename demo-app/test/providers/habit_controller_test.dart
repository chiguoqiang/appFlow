import 'package:demo_habit/core/date_utils.dart';
import 'package:demo_habit/data/habit_repository.dart';
import 'package:demo_habit/models/habit.dart';
import 'package:demo_habit/models/habit_data.dart';
import 'package:demo_habit/providers/habit_provider.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  ProviderContainer makeContainer(HabitData data) {
    final container = ProviderContainer(
      overrides: [
        habitRepositoryProvider.overrideWithValue(
          InMemoryHabitRepository(data),
        ),
        clockProvider.overrideWithValue(() => kToday),
      ],
    );
    addTearDown(container.dispose);
    return container;
  }

  Future<HabitController> readyController(ProviderContainer container) async {
    final future = container.read(habitControllerProvider.future);
    await future;
    return container.read(habitControllerProvider.notifier);
  }

  group('HabitController', () {
    test('打卡后写入一条记录并落盘', () async {
      final repo = InMemoryHabitRepository(
        HabitData(
          habits: [makeHabit(id: 'h1')],
          checkIns: [],
        ),
      );
      final container = ProviderContainer(
        overrides: [
          habitRepositoryProvider.overrideWithValue(repo),
          clockProvider.overrideWithValue(() => kToday),
        ],
      );
      addTearDown(container.dispose);

      await container.read(habitControllerProvider.future);
      await container.read(habitControllerProvider.notifier).toggleToday('h1');

      final state = container.read(habitControllerProvider).value!;
      expect(state.checkIns.length, 1);
      expect(state.checkIns.single.date, formatDateKey(kToday));
      expect(repo.lastSaved.checkIns.length, 1);
    });

    test('重复打卡幂等（同一天只保留一条），再次切换则取消', () async {
      final container = makeContainer(
        HabitData(
          habits: [makeHabit(id: 'h1')],
          checkIns: [],
        ),
      );
      final controller = await readyController(container);

      await controller.toggleToday('h1');
      await controller.toggleToday('h1');
      expect(container.read(habitControllerProvider).value!.checkIns, isEmpty);

      await controller.toggleToday('h1');
      await controller.toggleToday('h1');
      await controller.toggleToday('h1');
      expect(container.read(habitControllerProvider).value!.checkIns.length, 1);
    });

    test('新建习惯追加到列表', () async {
      final container = makeContainer(HabitData.empty);
      final controller = await readyController(container);

      await controller.upsertHabit(makeHabit(id: 'h1', name: '喝水'));
      await controller.upsertHabit(makeHabit(id: 'h2', name: '阅读'));

      final habits = container.read(habitControllerProvider).value!.habits;
      expect(habits.map((h) => h.id), ['h1', 'h2']);
    });

    test('编辑习惯保持位置不变', () async {
      final container = makeContainer(
        HabitData(
          habits: [
            makeHabit(id: 'h1', name: '喝水'),
            makeHabit(id: 'h2', name: '阅读'),
          ],
          checkIns: [],
        ),
      );
      final controller = await readyController(container);

      await controller.upsertHabit(makeHabit(id: 'h1', name: '多喝水'));

      final habits = container.read(habitControllerProvider).value!.habits;
      expect(habits.map((h) => h.id), ['h1', 'h2']);
      expect(habits.first.name, '多喝水');
    });

    test('删除习惯级联删除其打卡记录', () async {
      final container = makeContainer(
        HabitData(
          habits: [
            makeHabit(id: 'h1'),
            makeHabit(id: 'h2'),
          ],
          checkIns: [makeCheckIn('h1', kToday), makeCheckIn('h2', kToday)],
        ),
      );
      final controller = await readyController(container);

      await controller.deleteHabit('h1');

      final state = container.read(habitControllerProvider).value!;
      expect(state.habits.map((h) => h.id), ['h2']);
      expect(state.checkIns.every((c) => c.habitId == 'h2'), isTrue);
      expect(state.checkIns.length, 1);
    });

    test('重置清空全部数据', () async {
      final container = makeContainer(
        HabitData(
          habits: [makeHabit(id: 'h1')],
          checkIns: [makeCheckIn('h1', kToday)],
        ),
      );
      final controller = await readyController(container);

      await controller.resetAll();

      expect(container.read(habitControllerProvider).value, HabitData.empty);
    });

    test('不同习惯同日打卡互不影响', () async {
      final container = makeContainer(
        HabitData(
          habits: [
            makeHabit(id: 'h1'),
            makeHabit(id: 'h2'),
          ],
          checkIns: [],
        ),
      );
      final controller = await readyController(container);

      await controller.toggleToday('h1');

      final state = container.read(habitControllerProvider).value!;
      expect(state.checkIns.single.habitId, 'h1');
    });

    test('newHabitId 生成唯一 ID', () async {
      final container = makeContainer(HabitData.empty);
      final controller = await readyController(container);
      final ids = <String>{
        for (var i = 0; i < 20; i++) controller.newHabitId(),
      };
      expect(ids.length, 20);
    });
  });

  group('数据模型', () {
    test('Habit round-trip', () {
      final habit = makeHabit(
        id: 'h1',
        name: '阅读',
        frequencyType: FrequencyType.weeklyN,
        weeklyTarget: 5,
      );
      expect(Habit.fromJson(habit.toJson()), habit);
    });

    test('HabitData round-trip（含嵌套列表）', () {
      final data = HabitData(
        habits: [
          makeHabit(id: 'h1'),
          makeHabit(id: 'h2'),
        ],
        checkIns: [makeCheckIn('h1', kToday)],
      );
      expect(HabitData.fromJson(data.toJson()), data);
    });
  });
}
