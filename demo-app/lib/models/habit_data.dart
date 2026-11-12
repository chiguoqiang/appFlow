import 'package:flutter/foundation.dart';
import 'package:json_annotation/json_annotation.dart';

import 'check_in.dart';
import 'habit.dart';

part 'habit_data.g.dart';

/// 本地存储的根数据结构（单 JSON 文件）。
@JsonSerializable(explicitToJson: true)
class HabitData {
  const HabitData({required this.habits, required this.checkIns});

  static const HabitData empty = HabitData(habits: [], checkIns: []);

  /// 全部习惯。
  final List<Habit> habits;

  /// 全部打卡记录。
  final List<CheckIn> checkIns;

  factory HabitData.fromJson(Map<String, dynamic> json) =>
      _$HabitDataFromJson(json);

  Map<String, dynamic> toJson() => _$HabitDataToJson(this);

  HabitData copyWith({List<Habit>? habits, List<CheckIn>? checkIns}) {
    return HabitData(
      habits: habits ?? this.habits,
      checkIns: checkIns ?? this.checkIns,
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is HabitData &&
        listEquals(other.habits, habits) &&
        listEquals(other.checkIns, checkIns);
  }

  @override
  int get hashCode =>
      Object.hash(Object.hashAll(habits), Object.hashAll(checkIns));
}
