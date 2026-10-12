import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../auth/auth_provider.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      backgroundColor: const Color(0xFFFBF8FC),
      appBar: AppBar(
        title: const Text('Settings'),
        backgroundColor: const Color(0xFFFBF8FC),
        elevation: 0,
        iconTheme: const IconThemeData(color: Color(0xFF1B1B1E)),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1.0),
          child: Container(color: const Color(0xFFE4E4E7), height: 1.0),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.symmetric(vertical: 16),
        children: [
          _buildSectionHeader('Account'),
          ListTile(
            leading: const Icon(Icons.person_outline, color: Color(0xFF1B1B1E)),
            title: const Text('Authentication'),
            subtitle: const Text('Manage your account or log out'),
            trailing: const Icon(Icons.logout, color: Color(0xFFC62828)),
            onTap: () async {
              await ref.read(authProvider.notifier).logout();
              if (context.mounted) {
                context.go('/auth');
              }
            },
          ),
          const Divider(height: 32, color: Color(0xFFE4E4E7)),
          
          _buildSectionHeader('App Settings'),
          ListTile(
            leading: const Icon(Icons.palette_outlined, color: Color(0xFF1B1B1E)),
            title: const Text('Theme'),
            subtitle: const Text('Luminous Minimal (System Default)'),
            trailing: const Icon(Icons.check, color: Color(0xFF71787F)),
            onTap: () {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('CognAI exclusively uses the Luminous Minimal theme.')),
              );
            },
          ),
          const Divider(height: 32, color: Color(0xFFE4E4E7)),

          _buildSectionHeader('Data & Privacy'),
          ListTile(
            leading: const Icon(Icons.psychology_outlined, color: Color(0xFF1B1B1E)),
            title: const Text('Memory Controls'),
            subtitle: const Text('Manage your facts, goals, and persona drift'),
            trailing: const Icon(Icons.chevron_right, color: Color(0xFF71787F)),
            onTap: () {
              context.push('/memory');
            },
          ),
          const Divider(height: 32, color: Color(0xFFE4E4E7)),

          _buildSectionHeader('About'),
          ListTile(
            leading: const Icon(Icons.info_outline, color: Color(0xFF1B1B1E)),
            title: const Text('CognAI Version'),
            subtitle: const Text('v1.0.0 (Beta) - Research Grounded Model'),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w600,
          color: Color(0xFF004163),
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}
