import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/habit.dart';
import '../providers/habit_provider.dart';
import '../theme/app_theme.dart';
import '../theme/habit_presets.dart';
import '../widgets/app_card.dart';

/// PG-02 习惯编辑（创建 / 编辑）。
class EditHabitPage extends ConsumerStatefulWidget {
  const EditHabitPage({super.key, this.habit});

  /// 传入则为编辑态，为空为创建态。
  final Habit? habit;

  @override
  ConsumerState<EditHabitPage> createState() => _EditHabitPageState();
}

class _EditHabitPageState extends ConsumerState<EditHabitPage> {
  late final TextEditingController _nameController;
  late String _iconKey;
  late String _colorKey;
  late FrequencyType _frequencyType;
  late int _weeklyTarget;
  bool _saving = false;

  bool get _isEditing => widget.habit != null;

  @override
  void initState() {
    super.initState();
    final habit = widget.habit;
    _nameController = TextEditingController(text: habit?.name ?? '');
    _iconKey = habit?.iconKey ?? kHabitIcons.first.key;
    _colorKey = habit?.colorKey ?? kHabitColors.keys.first;
    _frequencyType = habit?.frequencyType ?? FrequencyType.daily;
    _weeklyTarget = habit?.weeklyTarget ?? 3;
    _nameController.addListener(_onNameChanged);
  }

  void _onNameChanged() => setState(() {});

  @override
  void dispose() {
    _nameController.removeListener(_onNameChanged);
    _nameController.dispose();
    super.dispose();
  }

  String get _trimmedName => _nameController.text.trim();

  /// 名称校验：1-20 字。
  bool get _isNameValid => _trimmedName.isNotEmpty && _trimmedName.length <= 20;

  /// 超长时才展示错误文案（空名仅禁用保存，避免首次进入就报错）。
  String? get _nameError => _trimmedName.length > 20 ? '名称需为 1-20 个字' : null;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: Text(_isEditing ? '编辑习惯' : '新建习惯'),
        actions: <Widget>[
          TextButton(
            onPressed: _isNameValid && !_saving ? _save : null,
            style: TextButton.styleFrom(
              foregroundColor: AppColors.primary,
              disabledForegroundColor: AppColors.textSecondary,
              textStyle: AppType.titleMedium,
            ),
            child: const Text('保存'),
          ),
          const SizedBox(width: AppSpacing.s),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.m,
          AppSpacing.s,
          AppSpacing.m,
          AppSpacing.l,
        ),
        children: <Widget>[
          _label('名称'),
          const SizedBox(height: AppSpacing.s),
          TextField(
            controller: _nameController,
            style: AppType.body,
            maxLines: 1,
            decoration: InputDecoration(
              hintText: '例如：每天喝 8 杯水',
              hintStyle: AppType.body.copyWith(color: AppColors.textSecondary),
              filled: true,
              fillColor: AppColors.surface,
              counterText: '${_nameController.text.length}/20',
              counterStyle: AppType.label,
              errorText: _nameError,
              errorStyle: AppType.label.copyWith(color: AppColors.error),
              contentPadding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.m,
                vertical: AppSpacing.s + AppSpacing.xs,
              ),
              border: _border(AppColors.divider),
              enabledBorder: _border(AppColors.divider),
              focusedBorder: _border(AppColors.primary),
              errorBorder: _border(AppColors.error),
              focusedErrorBorder: _border(AppColors.error),
            ),
          ),
          const SizedBox(height: AppSpacing.l),
          _label('图标'),
          const SizedBox(height: AppSpacing.s),
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: kHabitIcons.length,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 4,
              mainAxisExtent: 48,
              crossAxisSpacing: AppSpacing.s,
              mainAxisSpacing: AppSpacing.s,
            ),
            itemBuilder: (context, index) {
              final option = kHabitIcons[index];
              final selected = option.key == _iconKey;
              return InkWell(
                borderRadius: BorderRadius.circular(AppRadius.button),
                onTap: () => setState(() => _iconKey = option.key),
                child: Container(
                  decoration: BoxDecoration(
                    color: selected ? AppColors.primarySoft : AppColors.divider,
                    borderRadius: BorderRadius.circular(AppRadius.button),
                  ),
                  child: Icon(
                    option.icon,
                    size: 22,
                    color: selected
                        ? AppColors.primary
                        : AppColors.textSecondary,
                  ),
                ),
              );
            },
          ),
          const SizedBox(height: AppSpacing.l),
          _label('颜色'),
          const SizedBox(height: AppSpacing.s),
          Row(
            children: <Widget>[
              for (final entry in kHabitColors.entries)
                Padding(
                  padding: const EdgeInsets.only(right: AppSpacing.s),
                  child: _ColorDot(
                    color: entry.value,
                    selected: entry.key == _colorKey,
                    onTap: () => setState(() => _colorKey = entry.key),
                  ),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.l),
          _label('频率'),
          const SizedBox(height: AppSpacing.s),
          AppCard(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.s,
              vertical: AppSpacing.xs,
            ),
            child: Column(
              children: <Widget>[
                _FrequencyRow(
                  label: '每天',
                  selected: _frequencyType == FrequencyType.daily,
                  onTap: () =>
                      setState(() => _frequencyType = FrequencyType.daily),
                ),
                const Divider(),
                _FrequencyRow(
                  label: '每周 N 次',
                  selected: _frequencyType == FrequencyType.weeklyN,
                  onTap: () =>
                      setState(() => _frequencyType = FrequencyType.weeklyN),
                  trailing: _frequencyType == FrequencyType.weeklyN
                      ? _WeeklyStepper(
                          value: _weeklyTarget,
                          onChanged: (value) =>
                              setState(() => _weeklyTarget = value),
                        )
                      : null,
                ),
              ],
            ),
          ),
          if (_isEditing) ...<Widget>[
            const SizedBox(height: AppSpacing.l),
            TextButton(
              onPressed: _confirmDelete,
              style: TextButton.styleFrom(
                foregroundColor: AppColors.error,
                textStyle: AppType.body,
              ),
              child: const Text('删除习惯'),
            ),
          ],
        ],
      ),
    );
  }

  OutlineInputBorder _border(Color color) => OutlineInputBorder(
    borderRadius: BorderRadius.circular(AppRadius.input),
    borderSide: BorderSide(color: color),
  );

  Widget _label(String text) => Text(text, style: AppType.titleMedium);

  Future<void> _save() async {
    setState(() => _saving = true);
    final controller = ref.read(habitControllerProvider.notifier);
    final habit = Habit(
      id: widget.habit?.id ?? controller.newHabitId(),
      name: _trimmedName,
      iconKey: _iconKey,
      colorKey: _colorKey,
      frequencyType: _frequencyType,
      weeklyTarget: _weeklyTarget,
      createdAt: widget.habit?.createdAt ?? DateTime.now(),
    );
    await controller.upsertHabit(habit);
    if (!mounted) return;
    Navigator.of(context).pop();
  }

  Future<void> _confirmDelete() async {
    final habit = widget.habit;
    if (habit == null) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('删除习惯？', style: AppType.titleMedium),
        content: Text(
          '将同时删除「${habit.name}」的全部打卡记录，不可恢复。',
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
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    await ref.read(habitControllerProvider.notifier).deleteHabit(habit.id);
    if (!mounted) return;
    Navigator.of(context).pop();
  }
}

class _ColorDot extends StatelessWidget {
  const _ColorDot({
    required this.color,
    required this.selected,
    required this.onTap,
  });

  final Color color;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 32,
        height: 32,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(
            color: selected ? color : Colors.transparent,
            width: 2,
          ),
        ),
        child: Container(
          width: 24,
          height: 24,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
      ),
    );
  }
}

class _FrequencyRow extends StatelessWidget {
  const _FrequencyRow({
    required this.label,
    required this.selected,
    required this.onTap,
    this.trailing,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(AppRadius.button),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.s,
          vertical: AppSpacing.s,
        ),
        child: Row(
          children: <Widget>[
            Icon(
              selected
                  ? Icons.radio_button_checked
                  : Icons.radio_button_unchecked,
              size: 20,
              color: selected ? AppColors.primary : AppColors.textSecondary,
            ),
            const SizedBox(width: AppSpacing.s),
            Expanded(child: Text(label, style: AppType.body)),
            ?trailing,
          ],
        ),
      ),
    );
  }
}

class _WeeklyStepper extends StatelessWidget {
  const _WeeklyStepper({required this.value, required this.onChanged});

  final int value;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        IconButton(
          onPressed: value > 1 ? () => onChanged(value - 1) : null,
          tooltip: '减少',
          icon: const Icon(Icons.remove_circle_outline, size: 20),
          color: AppColors.primary,
          disabledColor: AppColors.divider,
          visualDensity: VisualDensity.compact,
        ),
        SizedBox(
          width: 24,
          child: Text(
            '$value',
            textAlign: TextAlign.center,
            style: AppType.titleMedium,
          ),
        ),
        IconButton(
          onPressed: value < 7 ? () => onChanged(value + 1) : null,
          tooltip: '增加',
          icon: const Icon(Icons.add_circle_outline, size: 20),
          color: AppColors.primary,
          disabledColor: AppColors.divider,
          visualDensity: VisualDensity.compact,
        ),
      ],
    );
  }
}
