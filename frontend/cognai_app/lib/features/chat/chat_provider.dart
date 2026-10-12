import 'dart:async';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/network/websocket_client.dart';
import '../../core/network/api_client.dart';

class AttachmentItem {
  final String id;
  final String fileName;
  final String fileType;
  final int fileSize;
  final bool isImage;
  final String? previewText;

  const AttachmentItem({
    required this.id,
    required this.fileName,
    required this.fileType,
    required this.fileSize,
    required this.isImage,
    this.previewText,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'file_name': fileName,
    'file_type': fileType,
    'file_size': fileSize,
    'is_image': isImage,
    'preview_text': previewText,
  };

  factory AttachmentItem.fromMap(Map<String, dynamic> map) {
    return AttachmentItem(
      id: map['id']?.toString() ?? '',
      fileName: map['file_name']?.toString() ?? '',
      fileType: map['file_type']?.toString() ?? '',
      fileSize: (map['file_size'] as num?)?.toInt() ?? 0,
      isImage: map['is_image'] == true,
      previewText: map['preview_text']?.toString(),
    );
  }
}

class ChatMessage {
  final String id;
  final String role; // 'user' or 'assistant'
  final String content;
  final DateTime timestamp;
  final Map<String, dynamic>? cognitiveTrace;
  final List<AttachmentItem>? attachments;

  ChatMessage({
    required this.id,
    required this.role,
    required this.content,
    required this.timestamp,
    this.cognitiveTrace,
    this.attachments,
  });
}

class ChatState {
  final List<ChatMessage> messages;
  final bool isSlowThinking;
  final bool isGenerating;
  final Map<String, dynamic>? latestCognitiveTrace;
  final String? sessionId;
  final bool isConnected;
  final List<AttachmentItem> pendingAttachments;
  final bool isUploadingAttachment;

  const ChatState({
    this.messages = const [],
    this.isSlowThinking = false,
    this.isGenerating = false,
    this.latestCognitiveTrace,
    this.sessionId,
    this.isConnected = false,
    this.pendingAttachments = const [],
    this.isUploadingAttachment = false,
  });

  ChatState copyWith({
    List<ChatMessage>? messages,
    bool? isSlowThinking,
    bool? isGenerating,
    Map<String, dynamic>? latestCognitiveTrace,
    String? sessionId,
    bool? isConnected,
    List<AttachmentItem>? pendingAttachments,
    bool? isUploadingAttachment,
  }) {
    return ChatState(
      messages: messages ?? this.messages,
      isSlowThinking: isSlowThinking ?? this.isSlowThinking,
      isGenerating: isGenerating ?? this.isGenerating,
      latestCognitiveTrace: latestCognitiveTrace ?? this.latestCognitiveTrace,
      sessionId: sessionId ?? this.sessionId,
      isConnected: isConnected ?? this.isConnected,
      pendingAttachments: pendingAttachments ?? this.pendingAttachments,
      isUploadingAttachment: isUploadingAttachment ?? this.isUploadingAttachment,
    );
  }
}

class ChatNotifier extends StateNotifier<ChatState> with WidgetsBindingObserver {
  final CognAIWebSocketClient _wsClient;
  StreamSubscription? _wsSubscription;
  StreamSubscription? _connSubscription;
  Timer? _streamWatchdogTimer;

  ChatNotifier(this._wsClient) : super(const ChatState()) {
    WidgetsBinding.instance.addObserver(this);
    _initializeWebSocket();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _wsClient.connect();
    } else if (state == AppLifecycleState.paused || state == AppLifecycleState.inactive) {
      _streamWatchdogTimer?.cancel();
      _wsClient.disconnect();
      if (this.state.isGenerating) {
        this.state = this.state.copyWith(
          isGenerating: false,
          isSlowThinking: false,
        );
      }
    }
  }

  void _initializeWebSocket() {
    _wsClient.connect();
    _wsSubscription = _wsClient.messageStream.listen(_handleIncomingMessage);
    _connSubscription = _wsClient.connectionStateStream.listen((isConnected) {
      if (!isConnected) {
        _streamWatchdogTimer?.cancel();
        state = state.copyWith(
          isConnected: false,
          isGenerating: false,
          isSlowThinking: false,
        );
      } else {
        state = state.copyWith(isConnected: true);
      }
    });
  }

  void _resetStreamWatchdog() {
    _streamWatchdogTimer?.cancel();
    _streamWatchdogTimer = Timer(const Duration(seconds: 40), () {
      if (state.isGenerating) {
        debugPrint("CognAI: Stream watchdog auto-reset after 40s inactivity.");
        state = state.copyWith(
          isGenerating: false,
          isSlowThinking: false,
        );
      }
    });
  }

  void cancelGeneration() {
    _streamWatchdogTimer?.cancel();
    state = state.copyWith(
      isGenerating: false,
      isSlowThinking: false,
    );
  }

  void _handleIncomingMessage(Map<String, dynamic> data) {
    if (data.containsKey('error')) {
      _streamWatchdogTimer?.cancel();
      state = state.copyWith(isGenerating: false, isSlowThinking: false);
      return;
    }

    final type = data['type'] as String?;

    // 1. Streaming started
    if (type == 'start') {
      _resetStreamWatchdog();
      final trace = data['cognitive_trace'] as Map<String, dynamic>?;
      final sessionId = data['session_id'] as String?;
      final assistantMessage = ChatMessage(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        role: 'assistant',
        content: '',
        timestamp: DateTime.now(),
        cognitiveTrace: trace,
      );
      state = state.copyWith(
        messages: [assistantMessage, ...state.messages],
        isGenerating: true,
        isSlowThinking: trace?['thinking_mode'] == 'SLOW_THINK',
        latestCognitiveTrace: trace,
        sessionId: sessionId ?? state.sessionId,
      );
      return;
    }

    // 2. Streaming token chunk
    if (type == 'chunk' || data.containsKey('delta')) {
      _resetStreamWatchdog();
      final delta = (data['delta'] as String?) ?? '';
      if (delta.isEmpty) return;

      List<ChatMessage> updatedMessages = List.from(state.messages);
      if (updatedMessages.isNotEmpty && updatedMessages.first.role == 'assistant') {
        final currentAsst = updatedMessages.first;
        updatedMessages[0] = ChatMessage(
          id: currentAsst.id,
          role: currentAsst.role,
          content: currentAsst.content + delta,
          timestamp: currentAsst.timestamp,
          cognitiveTrace: currentAsst.cognitiveTrace,
        );
      } else {
        updatedMessages.insert(
          0,
          ChatMessage(
            id: DateTime.now().millisecondsSinceEpoch.toString(),
            role: 'assistant',
            content: delta,
            timestamp: DateTime.now(),
          ),
        );
      }

      state = state.copyWith(
        messages: updatedMessages,
        isGenerating: true,
      );
      return;
    }

    // 3. Generation complete or full single response
    if (type == 'done' || data.containsKey('response')) {
      _streamWatchdogTimer?.cancel();
      final responseText = data['response'] as String? ?? '';
      final trace = data['cognitive_trace'] as Map<String, dynamic>?;
      final sessionId = data['session_id'] as String?;

      List<ChatMessage> updatedMessages = List.from(state.messages);
      if (updatedMessages.isNotEmpty && updatedMessages.first.role == 'assistant') {
        final currentAsst = updatedMessages.first;
        updatedMessages[0] = ChatMessage(
          id: currentAsst.id,
          role: currentAsst.role,
          content: responseText.isNotEmpty ? responseText : currentAsst.content,
          timestamp: currentAsst.timestamp,
          cognitiveTrace: trace ?? currentAsst.cognitiveTrace,
        );
      } else {
        updatedMessages.insert(
          0,
          ChatMessage(
            id: DateTime.now().millisecondsSinceEpoch.toString(),
            role: 'assistant',
            content: responseText,
            timestamp: DateTime.now(),
            cognitiveTrace: trace,
          ),
        );
      }

      state = state.copyWith(
        messages: updatedMessages,
        isGenerating: false,
        isSlowThinking: false,
        latestCognitiveTrace: trace ?? state.latestCognitiveTrace,
        sessionId: sessionId ?? state.sessionId,
      );
      return;
    }
  }

  void addPendingAttachment(AttachmentItem item) {
    state = state.copyWith(
      pendingAttachments: [...state.pendingAttachments, item],
    );
  }

  void removePendingAttachment(String id) {
    state = state.copyWith(
      pendingAttachments: state.pendingAttachments.where((a) => a.id != id).toList(),
    );
  }

  void clearPendingAttachments() {
    state = state.copyWith(pendingAttachments: const []);
  }

  void setUploadingAttachment(bool isUploading) {
    state = state.copyWith(isUploadingAttachment: isUploading);
  }

  void sendMessage(String text) {
    if (text.trim().isEmpty && state.pendingAttachments.isEmpty) return;

    final attachedList = List<AttachmentItem>.from(state.pendingAttachments);
    final attachedIds = attachedList.map((a) => a.id).toList();

    final userMessage = ChatMessage(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      role: 'user',
      content: text.isEmpty ? 'Please process the attached file(s).' : text,
      timestamp: DateTime.now(),
      attachments: attachedList.isNotEmpty ? attachedList : null,
    );

    // Pre-emptively detect if query might warrant slow-thinking
    final isComplex = text.length > 50 || text.contains('?') && text.contains('how') || attachedList.isNotEmpty;

    _resetStreamWatchdog();
    state = state.copyWith(
      messages: [userMessage, ...state.messages],
      isGenerating: true,
      isSlowThinking: isComplex,
      pendingAttachments: const [],
    );

    _wsClient.sendMessage(
      text.isEmpty ? 'Please process the attached file(s).' : text,
      attachmentIds: attachedIds,
    );
  }

  void startNewSession() {
    _streamWatchdogTimer?.cancel();
    // 1. Immediately reset state in the app so new chat opens instantly
    final localSessionId = 'session_${DateTime.now().millisecondsSinceEpoch}';
    state = state.copyWith(
      messages: [],
      sessionId: localSessionId,
      isGenerating: false,
      isSlowThinking: false,
      latestCognitiveTrace: null,
    );

    // 2. Link with backend asynchronously in the background
    apiClient.startNewSession().then((res) {
      if (res['session_id'] != null) {
        state = state.copyWith(sessionId: res['session_id']);
      }
    }).catchError((e) {
      debugPrint("Background session link error: $e");
    });
  }

  Future<void> loadSessionMessages(String sessionId) async {
    try {
      _streamWatchdogTimer?.cancel();
      state = state.copyWith(
        messages: [],
        sessionId: sessionId,
        isGenerating: false,
        isSlowThinking: false,
      ); // clear while loading
      final msgs = await apiClient.getSessionMessages(sessionId);
      
      final parsed = msgs.map((m) {
        DateTime ts;
        try {
          ts = m['created_at'] != null ? DateTime.parse(m['created_at']) : DateTime.now();
        } catch (_) {
          ts = DateTime.now();
        }

        List<AttachmentItem>? atts;
        if (m['attachments'] != null && m['attachments'] is List) {
          atts = (m['attachments'] as List)
              .map((a) => AttachmentItem.fromMap(a as Map<String, dynamic>))
              .toList();
        }

        return ChatMessage(
          id: m['id'].toString(),
          role: m['role'] ?? 'user',
          content: m['content'] ?? '',
          timestamp: ts,
          cognitiveTrace: m['cognitive_trace'],
          attachments: atts,
        );
      }).toList();
      
      // Strict chronological sorting:
      // Primary: timestamp ASC
      // Secondary: 'user' messages must precede 'assistant' messages
      parsed.sort((a, b) {
        final timeComp = a.timestamp.compareTo(b.timestamp);
        if (timeComp != 0) return timeComp;
        if (a.role == 'user' && b.role != 'user') return -1;
        if (a.role != 'user' && b.role == 'user') return 1;
        return a.id.compareTo(b.id);
      });
      
      // The ListView is reversed (index 0 is newest/bottom),
      // so reversing gives newest first for the ListView.
      state = state.copyWith(
        messages: parsed.reversed.toList(),
        isGenerating: false,
        isSlowThinking: false,
      );
    } catch (e) {
      debugPrint("Failed to load session messages: $e");
      state = state.copyWith(
        isGenerating: false,
        isSlowThinking: false,
      );
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _streamWatchdogTimer?.cancel();
    _wsSubscription?.cancel();
    _connSubscription?.cancel();
    _wsClient.dispose();
    super.dispose();
  }
}

final websocketClientProvider = Provider<CognAIWebSocketClient>((ref) {
  return CognAIWebSocketClient();
});

final chatProvider = StateNotifierProvider<ChatNotifier, ChatState>((ref) {
  final wsClient = ref.watch(websocketClientProvider);
  return ChatNotifier(wsClient);
});

final sessionsProvider = FutureProvider.autoDispose<List<dynamic>>((ref) async {
  return await apiClient.getSessions();
});
