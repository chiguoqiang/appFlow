import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/habit_provider.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';

/// PG-04 设置。
class SettingsPage extends ConsumerWidget {
  const SettingsPage({super.key});

  static const String appVersion = '1.0.0';

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: const Text('设置'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.m),
        children: <Widget>[
          const Padding(
            padding: EdgeInsets.only(left: AppSpacing.xs, bottom: AppSpacing.s),
            child: Text('数据', style: AppType.label),
          ),
          AppCard(
            padding: EdgeInsets.zero,
            child: ListTile(
              onTap: () => _confirmReset(context, ref),
              title: Text(
                '重置所有数据',
                style: AppType.body.copyWith(color: AppColors.error),
              ),
              trailing: const Icon(
                Icons.warning_amber_rounded,
                size: 20,
                color: AppColors.error,
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.m),
          const Padding(
            padding: EdgeInsets.only(left: AppSpacing.xs, bottom: AppSpacing.s),
            child: Text('关于', style: AppType.label),
          ),
          AppCard(
            padding: EdgeInsets.zero,
            child: const ListTile(
              title: Text('版本', style: AppType.body),
              trailing: Text(appVersion, style: AppType.label),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmReset(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('重置所有数据？', style: AppType.titleMedium),
        content: Text(
          '将删除全部习惯与打卡记录，此操作不可恢复。',
          style: AppType.body.copyWith(color: AppColors.textSecondary),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            style: TextButton.styleFrom(foregroundColor: AppColors.error),
            child: const Text('重置'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;

    await ref.read(habitControllerProvider.notifier).resetAll();
    if (!context.mounted) return;
    Navigator.of(context).maybePop(); // 返回首页（此时为空态）
  }
}
