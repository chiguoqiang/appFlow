/// 日期工具：全部按「本地自然日」运算，避免 DST 与跨月问题。
library;

/// 只保留年月日，丢弃时分秒。
DateTime dateOnly(DateTime d) => DateTime(d.year, d.month, d.day);

/// 日期加减天数（依赖 DateTime 构造器的规范化，自动处理跨月/跨年）。
DateTime addDays(DateTime d, int days) =>
    DateTime(d.year, d.month, d.day + days);

/// 前一天。
DateTime prevDay(DateTime d) => addDays(d, -1);

/// 本周起点（周一）。
DateTime startOfWeek(DateTime d) {
  final day = dateOnly(d);
  return addDays(day, -(day.weekday - 1));
}

/// 存储用日期键：yyyy-MM-dd。
String formatDateKey(DateTime d) {
  final y = d.year.toString().padLeft(4, '0');
  final m = d.month.toString().padLeft(2, '0');
  final day = d.day.toString().padLeft(2, '0');
  return '$y-$m-$day';
}

/// 星期文案（周一~周日）。
const List<String> weekdayLabels = <String>[
  '周一',
  '周二',
  '周三',
  '周四',
  '周五',
  '周六',
  '周日',
];

/// 首页头部日期文案，如「11月11日 周二」。
String formatHeaderDate(DateTime d) =>
    '${d.month}月${d.day}日 ${weekdayLabels[d.weekday - 1]}';
