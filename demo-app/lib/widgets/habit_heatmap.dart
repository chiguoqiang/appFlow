import 'package:flutter/material.dart';

import '../core/date_utils.dart';
import '../theme/app_theme.dart';

/// 近 30 天打卡热力图。
///
/// 7 列（周一~周日），行数按实际需要计算（30 天 + 起始偏移最多 6 → 最多 6 行）。
class HabitHeatmap extends StatelessWidget {
  const HabitHeatmap({
    super.key,
    required this.today,
    required this.checkedDateKeys,
    required this.color,
    this.days = 30,
  });

  final DateTime today;

  /// 已打卡日期键集合（yyyy-MM-dd）。
  final Set<String> checkedDateKeys;

  /// 习惯色。
  final Color color;

  /// 展示天数（默认近 30 天）。
  final int days;

  @override
  Widget build(BuildContext context) {
    final end = dateOnly(today);
    final start = addDays(end, -(days - 1));
    final leading = start.weekday - 1; // 周一为 0
    final totalSlots = leading + days;
    final rows = (totalSlots / 7).ceil();

    const double cell = 32;
    const double gap = 4;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        for (var r = 0; r < rows; r++)
          Padding(
            padding: EdgeInsets.only(bottom: r == rows - 1 ? 0 : gap),
            child: Row(
              children: <Widget>[
                for (var c = 0; c < 7; c++)
                  Padding(
                    padding: EdgeInsets.only(right: c == 6 ? 0 : gap),
                    child: _buildSlot(
                      index: r * 7 + c,
                      leading: leading,
                      start: start,
                      cell: cell,
                    ),
                  ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _buildSlot({
    required int index,
    required int leading,
    required DateTime start,
    required double cell,
  }) {
    final dayIndex = index - leading;
    if (dayIndex < 0 || dayIndex >= days) {
      return const SizedBox(width: 32, height: 32);
    }
    final date = addDays(start, dayIndex);
    final checked = checkedDateKeys.contains(formatDateKey(date));
    return Container(
      key: ValueKey<String>('heat-cell-${formatDateKey(date)}'),
      width: cell,
      height: cell,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: checked ? color : AppColors.divider,
        // 设计稿：热力图格子 32pt / 圆角 8（tokens 暂无 radius.cell，待补）
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        '${date.day}',
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w500,
          color: checked ? AppColors.surface : AppColors.textSecondary,
        ),
      ),
    );
  }
}
