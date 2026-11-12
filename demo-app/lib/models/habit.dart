import 'package:json_annotation/json_annotation.dart';

part 'habit.g.dart';

/// 习惯频率类型。
///
/// 序列化用 `wire` 字段值；未知值兜底为 [FrequencyType.daily]（字段级
/// [JsonKey.unknownEnumValue]），保证旧数据/脏数据不会导致解析崩溃。
@JsonEnum(valueField: 'wire')
enum FrequencyType {
  /// 每天。
  daily('daily'),

  /// 每周 N 次（N ∈ 1..7）。
  weeklyN('weekly_n');

  const FrequencyType(this.wire);

  /// 存储/传输用的字符串值。
  final String wire;
}

/// 习惯实体。
@JsonSerializable(explicitToJson: true)
class Habit {
  const Habit({
    required this.id,
    required this.name,
    required this.iconKey,
    required this.colorKey,
    required this.frequencyType,
    required this.weeklyTarget,
    required this.createdAt,
  });

  /// UUID。
  final String id;

  /// 名称（1-20 字）。
  final String name;

  /// 预设图标 key。
  final String iconKey;

  /// 预设色板 key。
  final String colorKey;

  /// 频率类型。
  @JsonKey(unknownEnumValue: FrequencyType.daily)
  final FrequencyType frequencyType;

  /// 每周目标次数，仅 [FrequencyType.weeklyN] 有效（1-7）。
  final int weeklyTarget;

  /// 创建时间。
  final DateTime createdAt;

  factory Habit.fromJson(Map<String, dynamic> json) => _$HabitFromJson(json);

  Map<String, dynamic> toJson() => _$HabitToJson(this);

  Habit copyWith({
    String? id,
    String? name,
    String? iconKey,
    String? colorKey,
    FrequencyType? frequencyType,
    int? weeklyTarget,
    DateTime? createdAt,
  }) {
    return Habit(
      id: id ?? this.id,
      name: name ?? this.name,
      iconKey: iconKey ?? this.iconKey,
      colorKey: colorKey ?? this.colorKey,
      frequencyType: frequencyType ?? this.frequencyType,
      weeklyTarget: weeklyTarget ?? this.weeklyTarget,
      createdAt: createdAt ?? this.createdAt,
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is Habit &&
        other.id == id &&
        other.name == name &&
        other.iconKey == iconKey &&
        other.colorKey == colorKey &&
        other.frequencyType == frequencyType &&
        other.weeklyTarget == weeklyTarget &&
        other.createdAt == createdAt;
  }

  @override
  int get hashCode => Object.hash(
    id,
    name,
    iconKey,
    colorKey,
    frequencyType,
    weeklyTarget,
    createdAt,
  );
}
