import 'dart:convert';
import 'dart:io';

import 'package:demo_habit/data/habit_repository.dart';
import 'package:demo_habit/models/check_in.dart';
import 'package:demo_habit/models/habit.dart';
import 'package:demo_habit/models/habit_data.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers.dart';

void main() {
  late Directory tempDir;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('demo_habit_test_');
  });

  tearDown(() async {
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  group('FileHabitRepository', () {
    test('无文件时返回空数据', () async {
      final repo = FileHabitRepository(directory: tempDir);
      final data = await repo.load();
      expect(data.habits, isEmpty);
      expect(data.checkIns, isEmpty);
    });

    test('保存后可完整读回（round-trip）', () async {
      final repo = FileHabitRepository(directory: tempDir);
      final habit = makeHabit(id: 'h1', name: '晨跑');
      final checkIn = makeCheckIn('h1', DateTime(2026, 11, 11));
      final data = HabitData(habits: [habit], checkIns: [checkIn]);

      await repo.save(data);
      final loaded = await repo.load();

      expect(loaded, data);
      expect(loaded.habits.single.name, '晨跑');
      expect(loaded.checkIns.single.date, '2026-11-11');
    });

    test('原子写入：不残留临时文件', () async {
      final repo = FileHabitRepository(directory: tempDir);
      await repo.save(
        HabitData(
          habits: [makeHabit(id: 'h1')],
          checkIns: [],
        ),
      );

      final names = tempDir
          .listSync()
          .map((e) => e.path.split('/').last)
          .toList();
      expect(names, contains('habits.json'));
      expect(names.where((n) => n.endsWith('.tmp')), isEmpty);
    });

    test('覆盖保存（全量替换）', () async {
      final repo = FileHabitRepository(directory: tempDir);
      await repo.save(
        HabitData(
          habits: [makeHabit(id: 'h1')],
          checkIns: [],
        ),
      );
      await repo.save(
        HabitData(
          habits: [makeHabit(id: 'h2')],
          checkIns: [],
        ),
      );

      final loaded = await repo.load();
      expect(loaded.habits.single.id, 'h2');
    });

    test('未知枚举值兜底为 daily（脏数据容错）', () async {
      final file = File('${tempDir.path}/habits.json');
      await file.writeAsString(
        jsonEncode(<String, dynamic>{
          'habits': <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'h1',
              'name': '旧数据',
              'iconKey': 'water',
              'colorKey': 'blue',
              'frequencyType': 'every_other_day', // 未知值
              'weeklyTarget': 3,
              'createdAt': '2026-01-01T00:00:00.000',
            },
          ],
          'checkIns': <Map<String, dynamic>>[],
        }),
      );

      final repo = FileHabitRepository(directory: tempDir);
      final loaded = await repo.load();
      expect(loaded.habits.single.frequencyType, FrequencyType.daily);
    });

    test('空文件按空数据处理', () async {
      final file = File('${tempDir.path}/habits.json');
      await file.writeAsString('');
      final repo = FileHabitRepository(directory: tempDir);
      expect(await repo.load(), HabitData.empty);
    });

    test('非法 JSON 抛 HabitRepositoryException', () async {
      final file = File('${tempDir.path}/habits.json');
      await file.writeAsString('{not json');
      final repo = FileHabitRepository(directory: tempDir);
      expect(repo.load(), throwsA(isA<HabitRepositoryException>()));
    });

    test('CheckIn 序列化/反序列化一致', () {
      final checkIn = CheckIn(
        id: 'c1',
        habitId: 'h1',
        date: '2026-11-11',
        createdAt: DateTime(2026, 11, 11, 8),
      );
      expect(CheckIn.fromJson(checkIn.toJson()), checkIn);
    });
  });
}
