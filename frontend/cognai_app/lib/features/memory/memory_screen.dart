import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/network/api_client.dart';
import '../chat/chat_provider.dart';
import 'package:go_router/go_router.dart';

class MemoryScreen extends ConsumerStatefulWidget {
  const MemoryScreen({super.key});

  @override
  ConsumerState<MemoryScreen> createState() => _MemoryScreenState();
}

class _MemoryScreenState extends ConsumerState<MemoryScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  bool _isLoading = true;
  List<dynamic> _goals = [];
  List<dynamic> _permanentMemories = [];
  List<dynamic> _episodes = [];
  Map<String, dynamic> _persona = {};

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
    _loadMemoryData();
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _loadMemoryData() async {
    setState(() => _isLoading = true);
    try {
      final results = await Future.wait([
        apiClient.getGoals(),
        apiClient.getPermanentMemories(),
        apiClient.getEpisodes(),
        apiClient.getPersona(),
      ]);
      setState(() {
        _goals = results[0] as List<dynamic>;
        _permanentMemories = results[1] as List<dynamic>;
        _episodes = results[2] as List<dynamic>;
        _persona = results[3] as Map<String, dynamic>;
        _isLoading = false;
      });
    } catch (e) {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _promptAddGoal() async {
    final titleController = TextEditingController();
    final descController = TextEditingController();

    final added = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add New Active Goal'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: titleController,
              decoration: const InputDecoration(labelText: 'Goal Title'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: descController,
              decoration: const InputDecoration(labelText: 'Description (Optional)'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Add Goal'),
          ),
        ],
      ),
    );

    if (added == true && titleController.text.trim().isNotEmpty) {
      await apiClient.createGoal(titleController.text.trim(), descController.text.trim());
      _loadMemoryData();
    }
  }

  Future<void> _triggerForgetMe() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Initiate Cascading Memory Purge?'),
        content: const Text(
          'This initiates a two-phase compliant purge. All episodic memories, permanent consolidated facts, '
          'goals, persona drift parameters, and Neo4j graph nodes will be permanently wiped.\n\n'
          'You will be immediately logged out.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Purge Everything (/forget-me)', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      try {
        await apiClient.forgetMe();
        if (!mounted) return;
        ref.invalidate(chatProvider);
        context.go('/auth');
      } catch (e) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error initiating deletion: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Memory & Privacy'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadMemoryData,
          ),
          IconButton(
            icon: const Icon(Icons.delete_forever, color: Colors.red),
            tooltip: 'Two-Phase /forget-me',
            onPressed: _triggerForgetMe,
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          labelColor: const Color(0xFF004163),
          indicatorColor: const Color(0xFF004163),
          tabs: const [
            Tab(text: 'Goals'),
            Tab(text: 'Permanent'),
            Tab(text: 'Episodes'),
            Tab(text: 'Persona'),
          ],
        ),
      ),
      floatingActionButton: _tabController.index == 0
          ? FloatingActionButton.extended(
              onPressed: _promptAddGoal,
              icon: const Icon(Icons.add),
              label: const Text('New Goal'),
            )
          : null,
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : TabBarView(
              controller: _tabController,
              children: [
                _buildGoalsTab(),
                _buildPermanentTab(),
                _buildEpisodesTab(),
                _buildPersonaTab(),
              ],
            ),
    );
  }

  Widget _buildEmptyState({
    required IconData icon,
    required String title,
    required String subtitle,
  }) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 36.0, vertical: 24.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: const BoxDecoration(
                color: Color(0xFFF0EDF1),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, size: 36, color: Color(0xFF004163)),
            ),
            const SizedBox(height: 16),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: Color(0xFF1B1B1E),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 13,
                color: Color(0xFF71787F),
                height: 1.4,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildGoalsTab() {
    if (_goals.isEmpty) {
      return _buildEmptyState(
        icon: Icons.flag_outlined,
        title: 'No Active Goals Yet',
        subtitle: 'Add a goal to guide longitudinal memory retention and retrieval priorities.',
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: _goals.length,
      separatorBuilder: (_, _) => const SizedBox(height: 12),
      itemBuilder: (context, index) {
        final g = _goals[index];
        return Card(
          child: ListTile(
            title: Text(g['title'] ?? 'Untitled Goal', style: const TextStyle(fontWeight: FontWeight.w600)),
            subtitle: Text(g['description'] ?? 'No description provided'),
            trailing: Chip(
              label: Text(g['status'] ?? 'active', style: const TextStyle(fontSize: 11)),
              backgroundColor: const Color(0xFFDAE2FD),
            ),
          ),
        );
      },
    );
  }

  Widget _buildPermanentTab() {
    if (_permanentMemories.isEmpty) {
      return _buildEmptyState(
        icon: Icons.auto_awesome_outlined,
        title: 'No Permanent Facts Yet',
        subtitle: 'Facts, identity traits, and user preferences are consolidated here over multiple sessions.',
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: _permanentMemories.length,
      separatorBuilder: (_, _) => const SizedBox(height: 12),
      itemBuilder: (context, index) {
        final f = _permanentMemories[index];
        return Card(
          child: ListTile(
            title: Text(f['fact'] ?? ''),
            subtitle: Text('Category: ${f['category']} | Accessed: ${f['access_count']}x'),
            trailing: Text('${((f['confidence'] ?? 1.0) * 100).toInt()}% conf', style: const TextStyle(fontSize: 12)),
          ),
        );
      },
    );
  }

  Widget _buildEpisodesTab() {
    if (_episodes.isEmpty) {
      return _buildEmptyState(
        icon: Icons.history_edu_outlined,
        title: 'No Closed Episodes Yet',
        subtitle: 'Sessions consolidate into episodic memories after 30 minutes of inactivity or upon starting a new chat.',
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.all(24),
      itemCount: _episodes.length,
      separatorBuilder: (_, _) => const SizedBox(height: 12),
      itemBuilder: (context, index) {
        final ep = _episodes[index];
        final valence = (ep['emotional_valence'] ?? 0.0) as num;
        final intensity = (ep['emotional_intensity'] ?? 0.0) as num;
        final surprise = (ep['surprise_score'] ?? 0.0) as num;

        return Card(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  ep['raw_summary'] ?? 'Session Episode',
                  style: const TextStyle(fontWeight: FontWeight.w500, fontSize: 14),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  children: [
                    Chip(
                      label: Text('Valence: ${valence.toStringAsFixed(2)}', style: const TextStyle(fontSize: 11)),
                      backgroundColor: valence >= 0 ? Colors.green.shade50 : Colors.red.shade50,
                    ),
                    Chip(
                      label: Text('Intensity: ${intensity.toStringAsFixed(2)}', style: const TextStyle(fontSize: 11)),
                      backgroundColor: const Color(0xFFE4E1E6),
                    ),
                    Chip(
                      label: Text('Surprise: ${surprise.toStringAsFixed(2)}', style: const TextStyle(fontSize: 11)),
                      backgroundColor: const Color(0xFFFFDCBD),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildPersonaTab() {
    if (_persona.isEmpty || _persona['signals'] == null) {
      return const Center(
        child: Text('No persona drift detected yet. Interact more to shape it.'),
      );
    }
    
    final signals = _persona['signals'] as Map<String, dynamic>;
    
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const Text(
          'Inferred Persona Drift',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        const Text(
          'These signals are implicitly extracted from your interactions and gently influence the companion\'s responses.',
          style: TextStyle(color: Colors.grey),
        ),
        const SizedBox(height: 24),
        ...signals.entries.map((e) {
          final val = (e.value as num).toDouble();
          return Padding(
            padding: const EdgeInsets.only(bottom: 24.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  e.key.replaceAll('_', ' ').toUpperCase(),
                  style: const TextStyle(
                    fontFamily: 'JetBrains Mono',
                    fontWeight: FontWeight.w600,
                    fontSize: 12,
                    letterSpacing: 1.1,
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    const Text('-1', style: TextStyle(fontSize: 12, color: Colors.grey)),
                    Expanded(
                      child: SliderTheme(
                        data: SliderTheme.of(context).copyWith(
                          disabledActiveTrackColor: const Color(0xFF075985),
                          disabledInactiveTrackColor: const Color(0xFFE4E4E7),
                          disabledThumbColor: const Color(0xFF075985),
                          trackHeight: 2.0,
                        ),
                        child: Slider(
                          value: val,
                          min: -1.0,
                          max: 1.0,
                          onChanged: null, // read-only
                        ),
                      ),
                    ),
                    const Text('+1', style: TextStyle(fontSize: 12, color: Colors.grey)),
                  ],
                ),
                Center(child: Text(val.toStringAsFixed(2), style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold))),
              ],
            ),
          );
        }),
      ],
    );
  }
}
