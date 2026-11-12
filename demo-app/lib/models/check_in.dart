import 'package:json_annotation/json_annotation.dart';

part 'check_in.g.dart';

/// 打卡记录。
///
/// `(habitId, date)` 唯一；[date] 为 `yyyy-MM-dd` 本地自然日，
/// 用字符串存储以规避时区序列化差异。
@JsonSerializable(explicitToJson: true)
class CheckIn {
  const CheckIn({
    required this.id,
    required this.habitId,
    required this.date,
    required this.createdAt,
  });

  /// UUID。
  final String id;

  /// 所属习惯 ID。
  final String habitId;

  /// 打卡日期键（yyyy-MM-dd）。
  final String date;

  /// 创建时间。
  final DateTime createdAt;

  factory CheckIn.fromJson(Map<String, dynamic> json) =>
      _$CheckInFromJson(json);

  Map<String, dynamic> toJson() => _$CheckInToJson(this);

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is CheckIn &&
        other.id == id &&
        other.habitId == habitId &&
        other.date == date &&
        other.createdAt == createdAt;
  }

  @override
  int get hashCode => Object.hash(id, habitId, date, createdAt);
}
