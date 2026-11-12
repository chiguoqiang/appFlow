import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// 通用卡片容器（surface 底 + card 圆角 + 轻阴影）。
class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(AppSpacing.m),
  });

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(AppRadius.card);
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: radius,
        boxShadow: AppShape.cardShadow,
      ),
      // 内层 Material 提供 ink 绘制表面：否则卡片内的 ListTile/InkWell
      // 会因外层 DecoratedBox 遮挡而看不到水波纹（Flutter 断言会直接报错）。
      child: Material(
        type: MaterialType.transparency,
        borderRadius: radius,
        clipBehavior: Clip.antiAlias,
        child: Padding(padding: padding, child: child),
      ),
    );
  }
}
