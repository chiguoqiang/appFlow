import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'data/habit_repository.dart';
import 'providers/habit_provider.dart';

void main() {
  runApp(
    ProviderScope(
      overrides: [
        habitRepositoryProvider.overrideWithValue(FileHabitRepository()),
      ],
      child: const DemoHabitApp(),
    ),
  );
}
