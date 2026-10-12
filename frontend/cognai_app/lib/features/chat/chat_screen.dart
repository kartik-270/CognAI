import 'dart:io' as io;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:file_picker/file_picker.dart';
import '../../core/network/api_client.dart';
import '../../shared/widgets/shimmer_loading.dart';
import '../../shared/widgets/latex_markdown.dart';
import 'chat_provider.dart';
import 'package:go_router/go_router.dart';

class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key});

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _pickAndUploadFiles() async {
    try {
      final result = await FilePicker.platform.pickFiles(
        allowMultiple: true,
        withData: true,
        type: FileType.custom,
        allowedExtensions: ['pdf', 'doc', 'docx', 'txt', 'md', 'json', 'csv', 'png', 'jpg', 'jpeg', 'webp'],
      );
      if (result == null || result.files.isEmpty) return;

      final notifier = ref.read(chatProvider.notifier);
      notifier.setUploadingAttachment(true);

      for (final platformFile in result.files) {
        List<int>? bytes = platformFile.bytes;
        if (bytes == null && !kIsWeb && platformFile.path != null) {
          final file = io.File(platformFile.path!);
          bytes = await file.readAsBytes();
        }
        if (bytes == null) continue;

        final res = await apiClient.uploadAttachment(
          bytes: bytes,
          fileName: platformFile.name,
          sessionId: ref.read(chatProvider).sessionId,
        );

        final item = AttachmentItem(
          id: res['id'],
          fileName: res['file_name'],
          fileType: res['file_type'],
          fileSize: (res['file_size'] as num?)?.toInt() ?? bytes.length,
          isImage: res['is_image'] == true,
          previewText: res['preview_text'],
        );
        notifier.addPendingAttachment(item);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to attach file: $e')),
        );
      }
    } finally {
      ref.read(chatProvider.notifier).setUploadingAttachment(false);
    }
  }

  void _sendMessage() {
    final text = _textController.text.trim();
    final hasAttachments = ref.read(chatProvider).pendingAttachments.isNotEmpty;
    if (text.isEmpty && !hasAttachments) return;
    HapticFeedback.lightImpact();
    ref.read(chatProvider.notifier).sendMessage(text);
    _textController.clear();
  }

  @override
  Widget build(BuildContext context) {
    final chatState = ref.watch(chatProvider);
    
    // Provide a light haptic tap when the assistant responds
    ref.listen<ChatState>(chatProvider, (prev, next) {
      if (prev != null && prev.messages.length < next.messages.length && next.messages.first.role == 'assistant') {
        HapticFeedback.lightImpact();
      }
    });

    return Scaffold(
      appBar: AppBar(
        title: const Text('CognAI'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            tooltip: 'New Chat',
            onPressed: () {
              ref.read(chatProvider.notifier).startNewSession();
              ref.invalidate(sessionsProvider);
            },
          ),
          IconButton(
            icon: const Icon(Icons.psychology),
            tooltip: 'Memory & Privacy',
            onPressed: () {
              context.push('/memory');
            },
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1.0),
          child: Container(color: const Color(0xFFE4E4E7), height: 1.0),
        ),
      ),
      drawer: _buildDrawer(context, ref),
      body: Column(
        children: [
          if (!chatState.isConnected)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 4),
              color: const Color(0xFFF4F4F5),
              child: const Text(
                'Reconnecting...',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'JetBrains Mono',
                  fontSize: 12,
                  color: Color(0xFF71787F),
                ),
              ),
            ),
          Expanded(
            child: chatState.messages.isEmpty
                ? Center(
                    child: Text(
                      'Start a conversation with CognAI.\nYour companion learns and consolidates long-term memory over time.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.grey.shade600, fontSize: 14),
                    ),
                  )
                : ListView.builder(
                    controller: _scrollController,
                    reverse: true,
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    itemCount: chatState.messages.length,
                    itemBuilder: (context, index) {
                      final msg = chatState.messages[index];
                      return _buildMessageBubble(msg);
                    },
                  ),
          ),
          
          if (chatState.isSlowThinking)
            const Align(
              alignment: Alignment.centerLeft,
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                child: SlowThinkIndicator(),
              ),
            ),
            
          _buildInputArea(context, chatState),
        ],
      ),
    );
  }

  Widget _buildMessageBubble(ChatMessage msg) {
    final isUser = msg.role == 'user';
    final trace = msg.cognitiveTrace;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6.0),
      child: Column(
        crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          Container(
            constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.82),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: isUser ? const Color(0xFF004163) : const Color(0xFFF0EDF1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                if (msg.attachments != null && msg.attachments!.isNotEmpty)
                  _buildMessageAttachments(msg.attachments!, isUser),
                if (isUser)
                  Text(
                    msg.content,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 15,
                      height: 1.4,
                    ),
                  )
                else
                  LatexMarkdown(
                    data: msg.content.isEmpty ? '...' : msg.content,
                    selectable: true,
                    styleSheet: MarkdownStyleSheet(
                      p: const TextStyle(
                        color: Color(0xFF1B1B1E),
                        fontSize: 15,
                        height: 1.4,
                      ),
                      strong: const TextStyle(
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF1B1B1E),
                      ),
                      em: const TextStyle(
                        fontStyle: FontStyle.italic,
                        color: Color(0xFF1B1B1E),
                      ),
                      h1: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF1B1B1E),
                      ),
                      h2: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF1B1B1E),
                      ),
                      h3: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF1B1B1E),
                      ),
                      listBullet: const TextStyle(
                        color: Color(0xFF1B1B1E),
                        fontSize: 15,
                      ),
                      code: TextStyle(
                        fontFamily: 'JetBrains Mono',
                        backgroundColor: Colors.black.withValues(alpha: 0.06),
                        fontSize: 13,
                      ),
                      blockquote: const TextStyle(
                        color: Color(0xFF555555),
                        fontSize: 14,
                        fontStyle: FontStyle.italic,
                      ),
                    ),
                  ),
              ],
            ),
          ),
          if (!isUser && trace != null && (trace['retrieved_memories_count'] ?? 0) > 0) ...[
            const SizedBox(height: 4),
            _buildTraceChip(
              label: '${trace['retrieved_memories_count']} memories used',
              color: const Color(0xFFE4E1E6),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildTraceChip({required String label, required Color color}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w500,
          fontFamily: 'JetBrains Mono',
          color: Color(0xFF1B1B1E),
        ),
      ),
    );
  }

  Widget _buildMessageAttachments(List<AttachmentItem> attachments, bool isUser) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Wrap(
        spacing: 6,
        runSpacing: 6,
        children: attachments.map((att) {
          return Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: isUser ? Colors.white.withValues(alpha: 0.15) : const Color(0xFFF1F5F9),
              borderRadius: BorderRadius.circular(6),
              border: Border.all(
                color: isUser ? Colors.white.withValues(alpha: 0.3) : const Color(0xFFE2E8F0),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  att.isImage
                      ? Icons.image
                      : (att.fileName.toLowerCase().endsWith('.pdf')
                          ? Icons.picture_as_pdf
                          : Icons.insert_drive_file),
                  size: 14,
                  color: isUser ? Colors.white : const Color(0xFF004163),
                ),
                const SizedBox(width: 6),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 160),
                  child: Text(
                    att.fileName,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: isUser ? Colors.white : const Color(0xFF1B1B1E),
                    ),
                  ),
                ),
              ],
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildPendingAttachmentChip(AttachmentItem att) {
    return Container(
      margin: const EdgeInsets.only(right: 8),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFCBD5E1)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            att.isImage
                ? Icons.image
                : (att.fileName.toLowerCase().endsWith('.pdf')
                    ? Icons.picture_as_pdf
                    : Icons.description),
            size: 16,
            color: const Color(0xFF004163),
          ),
          const SizedBox(width: 6),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 130),
            child: Text(
              att.fileName,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: Color(0xFF1B1B1E)),
            ),
          ),
          const SizedBox(width: 4),
          GestureDetector(
            onTap: () {
              ref.read(chatProvider.notifier).removePendingAttachment(att.id);
            },
            child: const Icon(Icons.close, size: 14, color: Color(0xFF888888)),
          ),
        ],
      ),
    );
  }

  Widget _buildInputArea(BuildContext context, ChatState chatState) {
    final pending = chatState.pendingAttachments;
    final isUploading = chatState.isUploadingAttachment;
    final isGenerating = chatState.isGenerating;

    return SafeArea(
      child: Container(
        decoration: const BoxDecoration(
          color: Color(0xFFFBF8FC),
          border: Border(top: BorderSide(color: Color(0xFFE4E4E7), width: 1)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (pending.isNotEmpty || isUploading)
              Container(
                height: 44,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  children: [
                    ...pending.map((att) => _buildPendingAttachmentChip(att)),
                    if (isUploading)
                      Container(
                        margin: const EdgeInsets.only(right: 8),
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF1F5F9),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: const Color(0xFFCBD5E1)),
                        ),
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            SizedBox(
                              width: 12,
                              height: 12,
                              child: CircularProgressIndicator(strokeWidth: 1.5, color: Color(0xFF004163)),
                            ),
                            SizedBox(width: 6),
                            Text('Uploading...', style: TextStyle(fontSize: 12, color: Color(0xFF64748B))),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Padding(
                    padding: const EdgeInsets.only(bottom: 2),
                    child: IconButton(
                      icon: const Icon(Icons.attach_file, color: Color(0xFF555555)),
                      tooltip: 'Attach document or image',
                      onPressed: isGenerating || isUploading ? null : _pickAndUploadFiles,
                    ),
                  ),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Container(
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFF004163), width: 1.5),
                      ),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                      child: TextField(
                        controller: _textController,
                        minLines: 1,
                        maxLines: 5,
                        keyboardType: TextInputType.multiline,
                        textInputAction: TextInputAction.newline,
                        decoration: const InputDecoration(
                          hintText: 'Message CognAI...',
                          border: InputBorder.none,
                          enabledBorder: InputBorder.none,
                          focusedBorder: InputBorder.none,
                          disabledBorder: InputBorder.none,
                          errorBorder: InputBorder.none,
                          isDense: true,
                          contentPadding: EdgeInsets.symmetric(vertical: 8),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Padding(
                    padding: const EdgeInsets.only(bottom: 2),
                    child: isGenerating
                        ? IconButton(
                            tooltip: 'Stop generation',
                            icon: Container(
                              width: 28,
                              height: 28,
                              decoration: BoxDecoration(
                                color: const Color(0xFF075985).withValues(alpha: 0.12),
                                shape: BoxShape.circle,
                              ),
                              child: const Center(
                                child: Icon(
                                  Icons.stop_rounded,
                                  size: 18,
                                  color: Color(0xFF075985),
                                ),
                              ),
                            ),
                            onPressed: () {
                              ref.read(chatProvider.notifier).cancelGeneration();
                            },
                          )
                        : IconButton(
                            tooltip: 'Send message',
                            icon: const Icon(Icons.send_rounded, color: Color(0xFF075985)),
                            onPressed: _sendMessage,
                          ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatSessionTime(DateTime dt) {
    final hour = dt.hour == 0 ? 12 : (dt.hour > 12 ? dt.hour - 12 : dt.hour);
    final minute = dt.minute.toString().padLeft(2, '0');
    final period = dt.hour >= 12 ? 'PM' : 'AM';
    return '$hour:$minute $period';
  }

  String _categorizeSession(DateTime dt) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final sessionDay = DateTime(dt.year, dt.month, dt.day);
    final diffDays = today.difference(sessionDay).inDays;

    if (diffDays <= 0) return 'Today';
    if (diffDays == 1) return 'Yesterday';
    if (diffDays <= 7) return 'This week';
    if (diffDays <= 30) return 'This month';
    return 'Older';
  }

  Widget _buildDrawer(BuildContext context, WidgetRef ref) {
    final sessionsAsync = ref.watch(sessionsProvider);
    
    return Drawer(
      backgroundColor: const Color(0xFFFBF8FC),
      child: Column(
        children: [
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Row(
                children: [
                  const Icon(Icons.chat_bubble_outline, color: Color(0xFF1B1B1E)),
                  const SizedBox(width: 12),
                  const Text(
                    'Chat History',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF1B1B1E),
                    ),
                  ),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.edit_square, color: Color(0xFF1B1B1E)),
                    onPressed: () {
                      ref.read(chatProvider.notifier).startNewSession();
                      ref.invalidate(sessionsProvider);
                      Navigator.pop(context);
                    },
                  ),
                ],
              ),
            ),
          ),
          const Divider(height: 1, color: Color(0xFFE4E4E7)),
          Expanded(
            child: sessionsAsync.when(
              data: (sessions) {
                if (sessions.isEmpty) {
                  return const Center(
                    child: Text(
                      'No past sessions.',
                      style: TextStyle(color: Color(0xFF71787F)),
                    ),
                  );
                }

                final categories = ['Today', 'Yesterday', 'This week', 'This month', 'Older'];
                final Map<String, List<dynamic>> grouped = {
                  for (var cat in categories) cat: [],
                };

                for (var session in sessions) {
                  DateTime dt = DateTime.now();
                  if (session['last_activity'] != null) {
                    try {
                      dt = DateTime.parse(session['last_activity']).toLocal();
                    } catch (_) {}
                  }
                  final cat = _categorizeSession(dt);
                  grouped[cat]?.add({'session': session, 'dt': dt});
                }

                return ListView(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  children: [
                    for (var cat in categories)
                      if ((grouped[cat]?.isNotEmpty ?? false)) ...[
                        Padding(
                          padding: const EdgeInsets.only(left: 16, right: 16, top: 14, bottom: 4),
                          child: Text(
                            cat.toUpperCase(),
                            style: const TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF71787F),
                              letterSpacing: 0.8,
                            ),
                          ),
                        ),
                        for (var item in grouped[cat]!)
                          ListTile(
                            dense: true,
                            leading: const Icon(Icons.chat_bubble_outline, size: 18, color: Color(0xFF004163)),
                            title: Text(
                              item['session']['title'] ?? 'Chat Session',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: Color(0xFF1B1B1E)),
                            ),
                            subtitle: Text(
                              _formatSessionTime(item['dt']),
                              style: const TextStyle(fontSize: 12, color: Color(0xFF71787F)),
                            ),
                            onTap: () {
                              ref.read(chatProvider.notifier).loadSessionMessages(item['session']['session_id']);
                              Navigator.pop(context);
                            },
                          ),
                      ],
                  ],
                );
              },
              loading: () => const Center(child: CircularProgressIndicator(strokeWidth: 2)),
              error: (e, st) => Center(child: Text('Error: $e')),
            ),
          ),
          const Divider(height: 1, color: Color(0xFFE4E4E7)),
          ListTile(
            leading: const Icon(Icons.settings, color: Color(0xFF1B1B1E)),
            title: const Text('Settings'),
            onTap: () {
              Navigator.pop(context);
              context.push('/settings');
            },
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}
