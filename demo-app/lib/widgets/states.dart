import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// 首页空态引导。
class HomeEmptyState extends StatelessWidget {
  const HomeEmptyState({super.key, required this.onCreate});

  final VoidCallback onCreate;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.l),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              Icons.event_available_outlined,
              size: 96,
              color: AppColors.textSecondary.withValues(alpha: 0.35),
            ),
            const SizedBox(height: AppSpacing.m),
            const Text('还没有习惯', style: AppType.titleMedium),
            const SizedBox(height: AppSpacing.xs),
            Text(
              '创建第一个习惯开始打卡吧',
              style: AppType.body.copyWith(color: AppColors.textSecondary),
            ),
            const SizedBox(height: AppSpacing.l),
            FilledButton(
              onPressed: onCreate,
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: AppColors.surface,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadius.button),
                ),
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.l,
                  vertical: AppSpacing.s + AppSpacing.xs,
                ),
                textStyle: AppType.titleMedium,
              ),
              child: const Text('＋ 创建习惯'),
            ),
          ],
        ),
      ),
    );
  }
}

/// 通用错误态（带重试）。
class ErrorState extends StatelessWidget {
  const ErrorState({super.key, required this.message, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const Icon(
            Icons.error_outline,
            size: 48,
            color: AppColors.textSecondary,
          ),
          const SizedBox(height: AppSpacing.m),
          Text(message, style: AppType.titleMedium),
          if (onRetry != null) ...<Widget>[
            const SizedBox(height: AppSpacing.m),
            FilledButton(
              onPressed: onRetry,
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: AppColors.surface,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadius.button),
                ),
              ),
              child: const Text('重试'),
            ),
          ],
        ],
      ),
    );
  }
}

/// 骨架卡片（加载态）。
class SkeletonCard extends StatelessWidget {
  const SkeletonCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 72,
      decoration: BoxDecoration(
        color: AppColors.divider,
        borderRadius: BorderRadius.circular(AppRadius.card),
      ),
    );
  }
}
