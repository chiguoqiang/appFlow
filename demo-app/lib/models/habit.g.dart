// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'habit.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

Habit _$HabitFromJson(Map<String, dynamic> json) => Habit(
  id: json['id'] as String,
  name: json['name'] as String,
  iconKey: json['iconKey'] as String,
  colorKey: json['colorKey'] as String,
  frequencyType: $enumDecode(
    _$FrequencyTypeEnumMap,
    json['frequencyType'],
    unknownValue: FrequencyType.daily,
  ),
  weeklyTarget: (json['weeklyTarget'] as num).toInt(),
  createdAt: DateTime.parse(json['createdAt'] as String),
);

Map<String, dynamic> _$HabitToJson(Habit instance) => <String, dynamic>{
  'id': instance.id,
  'name': instance.name,
  'iconKey': instance.iconKey,
  'colorKey': instance.colorKey,
  'frequencyType': _$FrequencyTypeEnumMap[instance.frequencyType]!,
  'weeklyTarget': instance.weeklyTarget,
  'createdAt': instance.createdAt.toIso8601String(),
};

const _$FrequencyTypeEnumMap = {
  FrequencyType.daily: 'daily',
  FrequencyType.weeklyN: 'weekly_n',
};
