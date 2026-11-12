import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import '../models/habit_data.dart';

/// 存储层异常。
class HabitRepositoryException implements Exception {
  HabitRepositoryException(this.message, [this.cause]);

  final String message;
  final Object? cause;

  @override
  String toString() => 'HabitRepositoryException: $message';
}

/// 数据仓库契约。
///
/// 抽象以便测试注入内存实现（不触碰真实文件系统）。
abstract interface class HabitRepository {
  /// 读取全部数据；无文件时返回 [HabitData.empty]。
  Future<HabitData> load();

  /// 全量保存（原子写入）。
  Future<void> save(HabitData data);
}

/// 基于单 JSON 文件的本地实现。
///
/// 写入策略：先写临时文件再 rename，避免写一半崩溃导致文件损坏。
class FileHabitRepository implements HabitRepository {
  FileHabitRepository({this.directory, this.fileName = 'habits.json'});

  /// 可注入目录（测试用）；为空时使用应用文档目录。
  final Directory? directory;
  final String fileName;

  Future<File> _resolveFile() async {
    final dir = directory ?? await getApplicationDocumentsDirectory();
    return File('${dir.path}/$fileName');
  }

  @override
  Future<HabitData> load() async {
    final file = await _resolveFile();
    if (!await file.exists()) return HabitData.empty;
    try {
      final raw = await file.readAsString();
      if (raw.trim().isEmpty) return HabitData.empty;
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) {
        throw HabitRepositoryException('存储文件格式非法（根节点不是对象）');
      }
      return HabitData.fromJson(decoded);
    } on HabitRepositoryException {
      rethrow;
    } catch (e) {
      throw HabitRepositoryException('读取本地数据失败', e);
    }
  }

  @override
  Future<void> save(HabitData data) async {
    final file = await _resolveFile();
    try {
      final tmp = File('${file.path}.tmp');
      await tmp.writeAsString(jsonEncode(data.toJson()), flush: true);
      await tmp.rename(file.path);
    } catch (e) {
      throw HabitRepositoryException('保存本地数据失败', e);
    }
  }
}

/// 内存实现（测试用 / 也可作为降级预案）。
class InMemoryHabitRepository implements HabitRepository {
  InMemoryHabitRepository([HabitData? initial])
    : _data = initial ?? HabitData.empty;

  HabitData _data;

  /// 最近一次保存的数据（便于断言）。
  HabitData get lastSaved => _data;

  @override
  Future<HabitData> load() async => _data;

  @override
  Future<void> save(HabitData data) async => _data = data;
}
