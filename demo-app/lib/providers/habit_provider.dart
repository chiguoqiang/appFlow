import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../core/date_utils.dart';
import '../data/habit_repository.dart';
import '../models/check_in.dart';
import '../models/habit.dart';
import '../models/habit_data.dart';

/// 时钟（便于测试注入固定日期）。
final Provider<DateTime Function()> clockProvider =
    Provider<DateTime Function()>((ref) => DateTime.now);

/// 数据仓库（main 中注入文件实现，测试注入内存实现）。
final Provider<HabitRepository> habitRepositoryProvider =
    Provider<HabitRepository>((ref) => FileHabitRepository());

/// 全局数据控制器。
final AsyncNotifierProvider<HabitController, HabitData>
habitControllerProvider = AsyncNotifierProvider<HabitController, HabitData>(
  HabitController.new,
);

/// 习惯数据控制器：唯一写入口，每次写入后立即落盘。
class HabitController extends AsyncNotifier<HabitData> {
  static const Uuid _uuid = Uuid();

  @override
  Future<HabitData> build() {
    return ref.watch(habitRepositoryProvider).load();
  }

  HabitData get _current => state.value ?? HabitData.empty;

  Future<void> _commit(HabitData next) async {
    await ref.read(habitRepositoryProvider).save(next);
    state = AsyncData(next);
  }

  /// 切换今日打卡状态（打卡 / 取消）。
  ///
  /// 同一习惯同一天最多一条记录（幂等）。
  Future<void> toggleToday(String habitId) async {
    final data = _current;
    final today = dateOnly(ref.read(clockProvider)());
    final key = formatDateKey(today);
    final exists = data.checkIns.any(
      (c) => c.habitId == habitId && c.date == key,
    );

    final nextCheckIns = <CheckIn>[
      for (final c in data.checkIns)
        if (!(c.habitId == habitId && c.date == key)) c,
    ];
    if (!exists) {
      nextCheckIns.add(
        CheckIn(
          id: _uuid.v4(),
          habitId: habitId,
          date: key,
          createdAt: DateTime.now(),
        ),
      );
    }
    await _commit(data.copyWith(checkIns: nextCheckIns));
  }

  /// 新建或更新习惯。
  Future<void> upsertHabit(Habit habit) async {
    final data = _current;
    final exists = data.habits.any((h) => h.id == habit.id);
    final nextHabits = <Habit>[
      for (final h in data.habits)
        if (h.id != habit.id) h,
      habit,
    ];
    // 保持创建时间排序稳定：新建追加在末尾即可。
    await _commit(
      data.copyWith(habits: exists ? _replace(data.habits, habit) : nextHabits),
    );
  }

  List<Habit> _replace(List<Habit> source, Habit habit) {
    return <Habit>[
      for (final h in source)
        if (h.id == habit.id) habit else h,
    ];
  }

  /// 删除习惯并级联删除其打卡记录。
  Future<void> deleteHabit(String habitId) async {
    final data = _current;
    await _commit(
      HabitData(
        habits: data.habits.where((h) => h.id != habitId).toList(),
        checkIns: data.checkIns.where((c) => c.habitId != habitId).toList(),
      ),
    );
  }

  /// 清空全部数据。
  Future<void> resetAll() async {
    await _commit(HabitData.empty);
  }

  /// 生成新习惯 ID。
  String newHabitId() => _uuid.v4();
}
