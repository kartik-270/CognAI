import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'core/theme.dart';
import 'core/routing/app_router.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await dotenv.load(fileName: ".env");
  } catch (_) {
    // .env is optional; falls back to defaults or system variables
  }
  // ProviderScope initializes Riverpod for State Management and DI
  runApp(const ProviderScope(child: CognAIApp()));
}


class CognAIApp extends ConsumerWidget {
  const CognAIApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'CognAI',
      theme: CognAITheme.lightTheme,
      routerConfig: router,
    );
  }
}
