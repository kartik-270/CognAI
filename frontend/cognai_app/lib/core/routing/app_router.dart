import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../features/auth/auth_provider.dart';
import '../../features/auth/auth_screen.dart';
import '../../features/chat/chat_screen.dart';
import '../../features/memory/memory_screen.dart';
import '../../features/settings/settings_screen.dart';
import '../../shared/widgets/splash_screen.dart';

final GlobalKey<NavigatorState> rootNavigatorKey = GlobalKey<NavigatorState>();

class RouterNotifier extends ChangeNotifier {
  final Ref _ref;

  RouterNotifier(this._ref) {
    _ref.listen<AuthState>(
      authProvider,
      (previous, next) {
        if (previous?.isAuthenticated != next.isAuthenticated ||
            previous?.isCheckingAuth != next.isCheckingAuth) {
          notifyListeners();
        }
      },
    );
  }
}

final routerNotifierProvider = Provider<RouterNotifier>((ref) {
  return RouterNotifier(ref);
});

final routerProvider = Provider<GoRouter>((ref) {
  final notifier = ref.watch(routerNotifierProvider);

  return GoRouter(
    navigatorKey: rootNavigatorKey,
    refreshListenable: notifier,
    initialLocation: '/splash',
    redirect: (context, state) {
      final authState = ref.read(authProvider);

      // 1. While reading token from secure storage, stay on splash screen
      if (authState.isCheckingAuth) {
        return state.matchedLocation == '/splash' ? null : '/splash';
      }

      final isAuth = authState.isAuthenticated;
      final isAuthPath = state.matchedLocation == '/auth' || state.matchedLocation == '/splash';

      // 2. Unauthenticated user accessing protected screens -> redirect to /auth
      if (!isAuth) {
        return state.matchedLocation == '/auth' ? null : '/auth';
      }

      // 3. Authenticated user on splash or login screen -> redirect to /chat
      if (isAuth && isAuthPath) {
        return '/chat';
      }

      // 4. Authenticated user navigating between /chat, /memory, /settings -> allow
      return null;
    },
    routes: [
      GoRoute(
        path: '/splash',
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(
        path: '/auth',
        builder: (context, state) => const AuthScreen(),
      ),
      GoRoute(
        path: '/chat',
        builder: (context, state) => const ChatScreen(),
      ),
      GoRoute(
        path: '/memory',
        builder: (context, state) => const MemoryScreen(),
      ),
      GoRoute(
        path: '/settings',
        builder: (context, state) => const SettingsScreen(),
      ),
    ],
  );
});
