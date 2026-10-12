import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'api_client.dart';

class CognAIWebSocketClient {
  WebSocketChannel? _channel;
  String get _baseUrl => 'ws://$defaultApiHost/ws/chat';
  final _storage = secureStorage;
  
  final StreamController<Map<String, dynamic>> _messageController = StreamController.broadcast();
  Stream<Map<String, dynamic>> get messageStream => _messageController.stream;

  final StreamController<bool> _connectionStateController = StreamController<bool>.broadcast();
  Stream<bool> get connectionStateStream => _connectionStateController.stream;

  bool _isConnecting = false;
  bool _intentionalDisconnect = false;
  final List<String> _offlineQueue = [];

  Future<void> connect() async {
    if (_isConnecting || _channel != null) return;
    _isConnecting = true;
    _intentionalDisconnect = false;

    try {
      final token = await _storage.read(key: 'jwt_token');
      if (token == null) {
        debugPrint("No auth token available, cannot connect WS.");
        _isConnecting = false;
        _connectionStateController.add(false);
        return;
      }

      final uri = Uri.parse('$_baseUrl?token=$token');
      _channel = WebSocketChannel.connect(uri);
      
      _connectionStateController.add(true);
      await _loadOfflineQueue();
      _flushOfflineQueue();

      _channel!.stream.listen(
        (data) {
          try {
            final decoded = jsonDecode(data);
            _messageController.add(decoded);
          } catch (e) {
            debugPrint("Error decoding WS message: $e");
          }
        },
        onDone: () {
          _channel = null;
          _isConnecting = false;
          _connectionStateController.add(false);
          if (!_intentionalDisconnect) _scheduleReconnect();
        },
        onError: (error) {
          _channel = null;
          _isConnecting = false;
          _connectionStateController.add(false);
          if (!_intentionalDisconnect) _scheduleReconnect();
        },
      );
    } catch (e) {
      _isConnecting = false;
      _connectionStateController.add(false);
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    Future.delayed(const Duration(seconds: 3), () {
      connect();
    });
  }

  void _flushOfflineQueue() {
    if (_offlineQueue.isEmpty || _channel == null) return;
    for (var msg in _offlineQueue) {
      _channel!.sink.add(msg);
    }
    _offlineQueue.clear();
    _saveOfflineQueue();
  }

  Future<void> _loadOfflineQueue() async {
    final data = await _storage.read(key: 'offline_queue');
    if (data != null) {
      try {
        final List<dynamic> decoded = jsonDecode(data);
        _offlineQueue.clear();
        _offlineQueue.addAll(decoded.cast<String>());
      } catch (e) {
        debugPrint("Error decoding offline queue: $e");
      }
    }
  }

  Future<void> _saveOfflineQueue() async {
    await _storage.write(key: 'offline_queue', value: jsonEncode(_offlineQueue));
  }

  void sendMessage(String text, {List<String>? attachmentIds}) {
    final payloadMap = <String, dynamic>{
      "prompt": text,
      "content": text,
      if (attachmentIds != null && attachmentIds.isNotEmpty)
        "attachment_ids": attachmentIds,
    };
    final payload = jsonEncode(payloadMap);
    if (_channel != null) {
      _channel!.sink.add(payload);
    } else {
      _offlineQueue.add(payload);
      _saveOfflineQueue();
      debugPrint("Socket offline: Message added to offline queue.");
    }
  }

  void disconnect() {
    _intentionalDisconnect = true;
    _channel?.sink.close();
    _channel = null;
    _isConnecting = false;
    _connectionStateController.add(false);
  }

  void dispose() {
    _channel?.sink.close();
    _messageController.close();
    _connectionStateController.close();
  }
}
