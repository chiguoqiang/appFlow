// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'habit_data.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

HabitData _$HabitDataFromJson(Map<String, dynamic> json) => HabitData(
  habits: (json['habits'] as List<dynamic>)
      .map((e) => Habit.fromJson(e as Map<String, dynamic>))
      .toList(),
  checkIns: (json['checkIns'] as List<dynamic>)
      .map((e) => CheckIn.fromJson(e as Map<String, dynamic>))
      .toList(),
);

Map<String, dynamic> _$HabitDataToJson(HabitData instance) => <String, dynamic>{
  'habits': instance.habits.map((e) => e.toJson()).toList(),
  'checkIns': instance.checkIns.map((e) => e.toJson()).toList(),
};
