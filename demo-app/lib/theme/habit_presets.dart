import 'package:flutter/material.dart';

import 'app_theme.dart';

/// 预设图标项。
class HabitIconOption {
  const HabitIconOption(this.key, this.icon);

  final String key;
  final IconData icon;
}

/// 12 枚预设图标（约束范围，避免自由发挥）。
const List<HabitIconOption> kHabitIcons = <HabitIconOption>[
  HabitIconOption('water', Icons.water_drop_outlined),
  HabitIconOption('run', Icons.directions_run),
  HabitIconOption('book', Icons.menu_book_outlined),
  HabitIconOption('sleep', Icons.bedtime_outlined),
  HabitIconOption('fitness', Icons.fitness_center),
  HabitIconOption('meditate', Icons.self_improvement),
  HabitIconOption('meal', Icons.restaurant_outlined),
  HabitIconOption('saving', Icons.savings_outlined),
  HabitIconOption('art', Icons.brush_outlined),
  HabitIconOption('music', Icons.music_note_outlined),
  HabitIconOption('code', Icons.code),
  HabitIconOption('pet', Icons.pets_outlined),
];

/// 6 色习惯色板（key → 颜色）。
const Map<String, Color> kHabitColors = <String, Color>{
  'blue': Color(0xFF4F6BED),
  'green': Color(0xFF30A46C),
  'orange': Color(0xFFF76B15),
  'purple': Color(0xFF8E4EC6),
  'pink': Color(0xFFD6409F),
  'teal': Color(0xFF12A594),
};

/// 兜底图标（未知 key 时）。
IconData iconFor(String key) {
  for (final option in kHabitIcons) {
    if (option.key == key) return option.icon;
  }
  return Icons.check_circle_outline;
}

/// 兜底颜色（未知 key 时）。
Color colorFor(String key) => kHabitColors[key] ?? AppColors.primary;

/// 危险操作色（导出便于页面复用同一 token）。
Color get dangerColor => AppColors.error;
