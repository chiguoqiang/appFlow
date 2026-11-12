// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'check_in.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

CheckIn _$CheckInFromJson(Map<String, dynamic> json) => CheckIn(
  id: json['id'] as String,
  habitId: json['habitId'] as String,
  date: json['date'] as String,
  createdAt: DateTime.parse(json['createdAt'] as String),
);

Map<String, dynamic> _$CheckInToJson(CheckIn instance) => <String, dynamic>{
  'id': instance.id,
  'habitId': instance.habitId,
  'date': instance.date,
  'createdAt': instance.createdAt.toIso8601String(),
};
