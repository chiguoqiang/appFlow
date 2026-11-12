import 'package:flutter/material.dart';

import 'pages/home_page.dart';
import 'theme/app_theme.dart';

/// 应用根组件。
class DemoHabitApp extends StatelessWidget {
  const DemoHabitApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '习惯打卡',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      home: const HomePage(),
    );
  }
}
