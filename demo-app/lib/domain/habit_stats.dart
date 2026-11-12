import '../core/date_utils.dart';
import '../models/check_in.dart';
import '../models/habit.dart';

/// 单个习惯的统计结果。
class HabitStats {
  const HabitStats({
    required this.streak,
    required this.total,
    required this.completionRate,
  });

  /// 连续天数（daily）/ 连续周数（weeklyN）。
  final int streak;

  /// 总打卡次数。
  final int total;

  /// 近 30 天完成率（0.0 - 1.0）。
  final double completionRate;

  /// 完成率百分比（四舍五入取整）。
  int get completionPercent => (completionRate * 100).round();

  static const HabitStats zero = HabitStats(
    streak: 0,
    total: 0,
    completionRate: 0,
  );
}

/// 统计口径（权威定义见 PRD 第 5 节「统计定义」）。
abstract final class HabitStatsCalculator {
  /// 某习惯的打卡日期集合。
  static Set<String> _datesOf(String habitId, List<CheckIn> allCheckIns) {
    return <String>{
      for (final c in allCheckIns)
        if (c.habitId == habitId) c.date,
    };
  }

  static int _countInRange(
    Set<String> dates,
    DateTime startInclusive,
    DateTime endExclusive,
  ) {
    var count = 0;
    var cursor = dateOnly(startInclusive);
    final end = dateOnly(endExclusive);
    while (cursor.isBefore(end)) {
      if (dates.contains(formatDateKey(cursor))) count++;
      cursor = addDays(cursor, 1);
    }
    return count;
  }

  /// 今日是否已打卡。
  static bool isCheckedToday(
    String habitId,
    List<CheckIn> allCheckIns,
    DateTime today,
  ) {
    final dates = _datesOf(habitId, allCheckIns);
    return dates.contains(formatDateKey(today));
  }

  /// 今日是否「应打卡」。
  ///
  /// daily → 1；weeklyN → 本周已打卡次数 < N 时为 1，否则 0。
  static bool isDueToday(
    Habit habit,
    List<CheckIn> allCheckIns,
    DateTime today,
  ) {
    if (habit.frequencyType == FrequencyType.daily) return true;
    final dates = _datesOf(habit.id, allCheckIns);
    final weekStart = startOfWeek(today);
    final weekCount = _countInRange(dates, weekStart, addDays(weekStart, 7));
    return weekCount < habit.weeklyTarget;
  }

  /// 计算统计。
  static HabitStats compute(
    Habit habit,
    List<CheckIn> allCheckIns,
    DateTime today,
  ) {
    final dates = _datesOf(habit.id, allCheckIns);
    final streak = habit.frequencyType == FrequencyType.daily
        ? _dailyStreak(habit, dates, today)
        : _weeklyStreak(habit, dates, today);

    // 总打卡 = 该习惯全部记录条数（等值于去重日期数，因 (habitId,date) 唯一）。
    final total = allCheckIns.where((c) => c.habitId == habit.id).length;

    return HabitStats(
      streak: streak,
      total: total,
      completionRate: _completionRate(habit, dates, today),
    );
  }

  /// daily：从今天（已打卡）或昨天（今天未打卡）往回连续打卡的天数。
  /// 今天未打卡不打断；漏打一天即清零。
  static int _dailyStreak(Habit habit, Set<String> dates, DateTime today) {
    final created = dateOnly(habit.createdAt);
    var cursor = dateOnly(today);
    if (!dates.contains(formatDateKey(cursor))) {
      cursor = prevDay(cursor);
    }
    var streak = 0;
    while (!cursor.isBefore(created) && dates.contains(formatDateKey(cursor))) {
      streak++;
      cursor = prevDay(cursor);
    }
    return streak;
  }

  /// weeklyN：连续周数。本周已满 N 计入；本周未满不影响历史周数。
  static int _weeklyStreak(Habit habit, Set<String> dates, DateTime today) {
    final target = habit.weeklyTarget;
    if (target <= 0) return 0;
    final created = dateOnly(habit.createdAt);
    final thisWeek = startOfWeek(today);

    var weeks = 0;

    // 本周：满 N 则计入（未满不打断）。
    final thisWeekCount = _countInRange(dates, thisWeek, addDays(thisWeek, 7));
    if (thisWeekCount >= target) weeks++;

    // 往回逐周。
    var weekStart = thisWeek;
    while (true) {
      weekStart = addDays(weekStart, -7);
      final weekEnd = addDays(weekStart, 7);
      // 该周完全早于创建日则停止。
      if (weekEnd.isBefore(created)) break;
      final count = _countInRange(dates, weekStart, weekEnd);
      if (count >= target) {
        weeks++;
      } else {
        break;
      }
    }
    return weeks;
  }

  /// 近 30 自然日完成率。
  static double _completionRate(
    Habit habit,
    Set<String> dates,
    DateTime today,
  ) {
    final end = addDays(dateOnly(today), 1);
    final start = addDays(dateOnly(today), -29);
    final actual = _countInRange(dates, start, end);
    final expected = habit.frequencyType == FrequencyType.daily
        ? 30
        : _expectedForWeekly(habit.weeklyTarget);
    final rate = actual / expected;
    return rate.clamp(0.0, 1.0).toDouble();
  }

  /// weeklyN 的 30 天应打卡次数：round(30/7×N)，下限 1。
  static int _expectedForWeekly(int n) {
    final raw = (30 / 7 * n).round();
    return raw < 1 ? 1 : raw;
  }

  /// 今日进度：已打卡数 / 应打卡数。
  static ({int done, int due}) todayProgress(
    List<Habit> habits,
    List<CheckIn> allCheckIns,
    DateTime today,
  ) {
    var done = 0;
    var due = 0;
    for (final habit in habits) {
      if (isCheckedToday(habit.id, allCheckIns, today)) done++;
      if (isDueToday(habit, allCheckIns, today)) due++;
    }
    return (done: done, due: due);
  }
}
