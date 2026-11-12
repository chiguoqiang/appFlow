import 'package:flutter/material.dart';

/// 颜色 tokens（权威值来源：03-design-delivery v1 ② Design Tokens）。
abstract final class AppColors {
  static const Color primary = Color(0xFF4F6BED);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color background = Color(0xFFF6F7FB);
  static const Color textPrimary = Color(0xFF1A1D29);
  static const Color textSecondary = Color(0xFF8A90A3);
  static const Color divider = Color(0xFFECEDF3);
  static const Color error = Color(0xFFE5484D);
  static const Color success = Color(0xFF30A46C);

  /// 主色 10% 底（chip / 选中态）。
  static Color primarySoft = primary.withValues(alpha: 0.1);
}

/// 文字 tokens。
abstract final class AppType {
  /// 行高倍数（token: typography.lineHeightMultiplier）。
  static const double _lh = 1.4;

  static const TextStyle display = TextStyle(
    fontSize: 28,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.5,
    height: _lh,
    color: AppColors.textPrimary,
  );

  static const TextStyle titleLarge = TextStyle(
    fontSize: 20,
    fontWeight: FontWeight.w600,
    height: _lh,
    color: AppColors.textPrimary,
  );

  static const TextStyle titleMedium = TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.w600,
    height: _lh,
    color: AppColors.textPrimary,
  );

  static const TextStyle body = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w400,
    height: _lh,
    color: AppColors.textPrimary,
  );

  static const TextStyle label = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w500,
    height: _lh,
    color: AppColors.textSecondary,
  );
}

/// 间距 tokens。
abstract final class AppSpacing {
  static const double xs = 4;
  static const double s = 8;
  static const double m = 16;
  static const double l = 24;
}

/// 圆角 tokens。
abstract final class AppRadius {
  static const double card = 16;
  static const double button = 12;
  static const double input = 12;
  static const double chip = 999;
}

/// 其他形状/尺寸 tokens。
abstract final class AppShape {
  static const double touchTargetMin = 44;
  static const double cardShadowOpacity = 0.04;
  static const double habitIconBgOpacity = 0.2;
  static const double checkedCardOpacity = 0.55;

  static const List<BoxShadow> cardShadow = <BoxShadow>[
    BoxShadow(
      color: Color(0x0A1A1D29), // rgba(26,29,41,0.04)
      blurRadius: 8,
      offset: Offset(0, 2),
    ),
  ];
}

/// 全局主题。
ThemeData buildAppTheme() {
  final base = ThemeData(useMaterial3: true, brightness: Brightness.light);
  return base.copyWith(
    scaffoldBackgroundColor: AppColors.background,
    colorScheme: base.colorScheme.copyWith(
      primary: AppColors.primary,
      surface: AppColors.surface,
      error: AppColors.error,
    ),
    textTheme: base.textTheme.copyWith(
      displaySmall: AppType.display,
      titleLarge: AppType.titleLarge,
      titleMedium: AppType.titleMedium,
      bodyMedium: AppType.body,
      labelSmall: AppType.label,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.background,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: AppType.titleLarge,
      iconTheme: IconThemeData(color: AppColors.textPrimary),
    ),
    dividerTheme: const DividerThemeData(
      color: AppColors.divider,
      thickness: 1,
      space: 1,
    ),
    splashFactory: InkSparkle.splashFactory,
  );
}
