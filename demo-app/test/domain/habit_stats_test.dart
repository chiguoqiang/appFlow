import 'package:demo_habit/core/date_utils.dart';
import 'package:demo_habit/domain/habit_stats.dart';
import 'package:demo_habit/models/check_in.dart';
import 'package:demo_habit/models/habit.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  final today = dateOnly(kToday);

  List<CheckIn> dailyCheckIns(String habitId, int days) {
    return <CheckIn>[
      for (var i = 0; i < days; i++) makeCheckIn(habitId, addDays(today, -i)),
    ];
  }

  group('daily streak', () {
    test('今天已打卡：从今天起算连续天数', () {
      final habit = makeHabit(id: 'h1');
      final checkIns = dailyCheckIns('h1', 3);
      final stats = HabitStatsCalculator.compute(habit, checkIns, today);
      expect(stats.streak, 3);
      expect(stats.total, 3);
    });

    test('今天未打卡不打断：从昨天回溯', () {
      final habit = makeHabit(id: 'h1');
      final checkIns = <CheckIn>[
        makeCheckIn('h1', addDays(today, -1)),
        makeCheckIn('h1', addDays(today, -2)),
      ];
      final stats = HabitStatsCalculator.compute(habit, checkIns, today);
      expect(stats.streak, 2);
    });

    test('中断即清零：漏打一天后只算最近连续段', () {
      final habit = makeHabit(id: 'h1');
      final checkIns = <CheckIn>[
        makeCheckIn('h1', today),
        // 昨天漏打
        makeCheckIn('h1', addDays(today, -2)),
        makeCheckIn('h1', addDays(today, -3)),
      ];
      final stats = HabitStatsCalculator.compute(habit, checkIns, today);
      expect(stats.streak, 1);
    });

    test('无任何打卡时 streak 为 0', () {
      final habit = makeHabit(id: 'h1');
      final stats = HabitStatsCalculator.compute(habit, const [], today);
      expect(stats.streak, 0);
      expect(stats.total, 0);
      expect(stats.completionPercent, 0);
    });

    test('不越界到创建日之前', () {
      final habit = makeHabit(id: 'h1', createdAt: addDays(today, -1));
      final checkIns = <CheckIn>[
        makeCheckIn('h1', today),
        makeCheckIn('h1', addDays(today, -1)),
        // 创建日之前的打卡（脏数据）不应计入
        makeCheckIn('h1', addDays(today, -2)),
      ];
      final stats = HabitStatsCalculator.compute(habit, checkIns, today);
      expect(stats.streak, 2);
    });
  });

  group('weekly streak', () {
    /// 生成本周内的第 offset 天打卡（周一为 0）。
    CheckIn weekCheckIn(String habitId, int weekOffset, int dayOfWeek) {
      final weekStart = addDays(startOfWeek(today), weekOffset * 7);
      return makeCheckIn(habitId, addDays(weekStart, dayOfWeek));
    }

    test('连续周数：本周满 + 上周满 → 2', () {
      final habit = makeHabit(
        id: 'h1',
        frequencyType: FrequencyType.weeklyN,
        weeklyTarget: 2,
      );
      final checkIns = <CheckIn>[
        weekCheckIn('h1', 0, 0),
        weekCheckIn('h1', 0, 1),
        weekCheckIn('h1', -1, 0),
        weekCheckIn('h1', -1, 1),
      ];
      final stats = HabitStatsCalculator.compute(habit, checkIns, today);
      expect(stats.streak, 2);
    });

    test('本周未满不影响历史周数', () {
      final habit = makeHabit(
        id: 'h1',
        frequencyType: FrequencyType.weeklyN,
        weeklyTarget: 2,
      );
      final checkIns = <CheckIn>[
        weekCheckIn('h1', 0, 0), // 本周仅 1 次，未满
        weekCheckIn('h1', -1, 0),
        weekCheckIn('h1', -1, 1),
      ];
      final stats = HabitStatsCalculator.compute(habit, checkIns, today);
      expect(stats.streak, 1);
    });

    test('中间某周不足即中断', () {
      final habit = makeHabit(
        id: 'h1',
        frequencyType: FrequencyType.weeklyN,
        weeklyTarget: 2,
      );
      final checkIns = <CheckIn>[
        weekCheckIn('h1', 0, 0),
        weekCheckIn('h1', 0, 1),
        weekCheckIn('h1', -2, 0), // 上周不足 → 断
        weekCheckIn('h1', -2, 1),
      ];
      final stats = HabitStatsCalculator.compute(habit, checkIns, today);
      expect(stats.streak, 1);
    });
  });

  group('completion rate (30d)', () {
    test('daily：15/30 → 50%', () {
      final habit = makeHabit(id: 'h1');
      final checkIns = <CheckIn>[
        for (var i = 0; i < 15; i++) makeCheckIn('h1', addDays(today, -i * 2)),
      ];
      final stats = HabitStatsCalculator.compute(habit, checkIns, today);
      expect(stats.completionPercent, 50);
    });

    test('weeklyN=4：分母 round(30/7×4)=17', () {
      final habit = makeHabit(
        id: 'h1',
        frequencyType: FrequencyType.weeklyN,
        weeklyTarget: 4,
      );
      final checkIns = <CheckIn>[
        for (var i = 0; i < 17; i++) makeCheckIn('h1', addDays(today, -i)),
      ];
      final stats = HabitStatsCalculator.compute(habit, checkIns, today);
      expect(stats.completionPercent, 100);
    });

    test('weeklyN=1：分母 round(4.28)=4', () {
      final habit = makeHabit(
        id: 'h1',
        frequencyType: FrequencyType.weeklyN,
        weeklyTarget: 1,
      );
      final checkIns = <CheckIn>[
        for (var i = 0; i < 2; i++) makeCheckIn('h1', addDays(today, -i)),
      ];
      final stats = HabitStatsCalculator.compute(habit, checkIns, today);
      expect(stats.completionPercent, 50);
    });

    test('weeklyN=7：分母 30（等效每天）', () {
      final habit = makeHabit(
        id: 'h1',
        frequencyType: FrequencyType.weeklyN,
        weeklyTarget: 7,
      );
      final checkIns = <CheckIn>[
        for (var i = 0; i < 30; i++) makeCheckIn('h1', addDays(today, -i)),
      ];
      final stats = HabitStatsCalculator.compute(habit, checkIns, today);
      expect(stats.completionPercent, 100);
    });

    test('超过应打卡次数时上限 100%', () {
      final habit = makeHabit(id: 'h1');
      final stats = HabitStatsCalculator.compute(habit, <CheckIn>[
        makeCheckIn('h1', today),
      ], today);
      expect(stats.completionPercent, 3);
    });
  });

  group('isDueToday / todayProgress', () {
    test('daily 恒为应打卡', () {
      final habit = makeHabit(id: 'h1');
      expect(HabitStatsCalculator.isDueToday(habit, const [], today), isTrue);
    });

    test('weeklyN 本周未满 → 应打卡；已满 → 不应打卡', () {
      final habit = makeHabit(
        id: 'h1',
        frequencyType: FrequencyType.weeklyN,
        weeklyTarget: 2,
      );
      final weekStart = startOfWeek(today);
      final twoThisWeek = <CheckIn>[
        makeCheckIn('h1', weekStart),
        makeCheckIn('h1', addDays(weekStart, 1)),
      ];
      expect(HabitStatsCalculator.isDueToday(habit, const [], today), isTrue);
      expect(
        HabitStatsCalculator.isDueToday(habit, twoThisWeek, today),
        isFalse,
      );
    });

    test('今日进度：done/due 分别统计', () {
      final daily = makeHabit(id: 'd1', name: '喝水');
      final weekly = makeHabit(
        id: 'w1',
        name: '跑步',
        frequencyType: FrequencyType.weeklyN,
        weeklyTarget: 2,
      );
      final weekStart = startOfWeek(today);
      final checkIns = <CheckIn>[
        makeCheckIn('d1', today),
        makeCheckIn('w1', weekStart),
        makeCheckIn('w1', addDays(weekStart, 1)),
      ];
      final progress = HabitStatsCalculator.todayProgress(
        <Habit>[daily, weekly],
        checkIns,
        today,
      );
      expect(progress.done, 1);
      expect(progress.due, 1); // weekly 本周已满 → 不计应打卡
    });
  });
}
