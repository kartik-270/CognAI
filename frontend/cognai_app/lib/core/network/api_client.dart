import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

String get defaultApiHost {
  final fromDotEnv = dotenv.isInitialized ? dotenv.maybeGet('API_HOST') : null;
  if (fromDotEnv != null && fromDotEnv.trim().isNotEmpty) return fromDotEnv.trim();

  const custom = String.fromEnvironment('API_HOST');
  if (custom.isNotEmpty) return custom;
  if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
    return '10.0.2.2:8000';
  }
  return 'localhost:8000';
}

String? get configuredGoogleClientId {
  final fromDotEnv = dotenv.isInitialized ? dotenv.maybeGet('GOOGLE_CLIENT_ID') : null;
  if (fromDotEnv != null && fromDotEnv.trim().isNotEmpty) return fromDotEnv.trim();

  const custom = String.fromEnvironment('GOOGLE_CLIENT_ID');
  if (custom.isNotEmpty) return custom;
  return null;
}

const FlutterSecureStorage secureStorage = FlutterSecureStorage(
  aOptions: AndroidOptions(
    encryptedSharedPreferences: true,
    resetOnError: true,
  ),
  iOptions: IOSOptions(
    accessibility: KeychainAccessibility.first_unlock,
  ),
);

class ApiClient {
  static String get baseUrl => 'http://$defaultApiHost';
  final Dio dio;
  final FlutterSecureStorage storage;

  ApiClient({Dio? dioClient, FlutterSecureStorage? secureStorageClient})
      : dio = dioClient ?? Dio(BaseOptions(baseUrl: 'http://$defaultApiHost')),
        storage = secureStorageClient ?? secureStorage {
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          try {
            final token = await storage.read(key: 'jwt_token');
            if (token != null && token.isNotEmpty) {
              options.headers['Authorization'] = 'Bearer $token';
            }
          } catch (e) {
            debugPrint("Error reading token in request interceptor: $e");
          }
          return handler.next(options);
        },
        onError: (DioException e, handler) {
          return handler.next(e);
        },
      ),
    );
  }

  // Authentication Endpoints
  Future<Map<String, dynamic>> registerStep1(String email) async {
    final response = await dio.post('/auth/register/step1', data: {
      'email': email,
    });
    return response.data;
  }

  Future<Map<String, dynamic>> registerStep2(String email, String password, String confirmPassword) async {
    final response = await dio.post('/auth/register/step2', data: {
      'email': email,
      'password': password,
      'confirm_password': confirmPassword,
    });
    return response.data;
  }

  Future<Map<String, dynamic>> verifyOtp(String email, String otp) async {
    final response = await dio.post('/auth/register/verify-otp', data: {
      'email': email,
      'otp': otp,
    });
    return response.data;
  }

  Future<Map<String, dynamic>> resendRegisterOtp(String email) async {
    final response = await dio.post('/auth/register/resend-otp', data: {
      'email': email,
    });
    return response.data;
  }

  Future<Map<String, dynamic>> forgotPassword(String email) async {
    final response = await dio.post('/auth/forgot-password', data: {
      'email': email,
    });
    return response.data;
  }

  Future<Map<String, dynamic>> resetPassword(String email, String otp, String newPassword, String confirmPassword) async {
    final response = await dio.post('/auth/reset-password', data: {
      'email': email,
      'otp': otp,
      'new_password': newPassword,
      'confirm_password': confirmPassword,
    });
    return response.data;
  }

  Future<String> login(String email, String password) async {
    final formData = FormData.fromMap({
      'username': email,
      'password': password,
    });
    final response = await dio.post('/auth/login', data: formData);
    final token = response.data['access_token'] as String;
    await storage.write(key: 'jwt_token', value: token);
    return token;
  }

  Future<String> loginWithGoogleToken({String? idToken, String? accessToken}) async {
    final response = await dio.post('/auth/google', data: {
      'id_token': idToken,
      'access_token': accessToken,
    });
    final token = response.data['access_token'] as String;
    await storage.write(key: 'jwt_token', value: token);
    return token;
  }

  Future<String?> fetchRemoteGoogleClientId() async {
    try {
      final response = await dio.get('/auth/config');
      return response.data['google_client_id'] as String?;
    } catch (_) {
      return null;
    }
  }

  Future<void> logout() async {
    await storage.delete(key: 'jwt_token');
  }

  Future<bool> hasToken() async {
    try {
      final token = await storage.read(key: 'jwt_token');
      return token != null && token.trim().isNotEmpty;
    } catch (e) {
      debugPrint("Error reading jwt_token in hasToken: $e");
      return false;
    }
  }

  Future<List<dynamic>> getSessions() async {
    final response = await dio.get('/chat/sessions');
    return response.data as List<dynamic>;
  }

  Future<List<dynamic>> getSessionMessages(String sessionId) async {
    final response = await dio.get('/chat/sessions/$sessionId/messages');
    return response.data as List<dynamic>;
  }

  Future<Map<String, dynamic>> startNewSession() async {
    final response = await dio.post('/chat/sessions/new');
    return response.data as Map<String, dynamic>;
  }

  // Attachment Upload
  Future<Map<String, dynamic>> uploadAttachment({
    required List<int> bytes,
    required String fileName,
    String? sessionId,
  }) async {
    final formData = FormData.fromMap({
      'file': MultipartFile.fromBytes(bytes, filename: fileName),
      'session_id': ?sessionId,
    });
    final response = await dio.post('/chat/upload-attachment', data: formData);
    return response.data as Map<String, dynamic>;
  }

  // Memory & Goals Endpoints
  Future<List<dynamic>> getPermanentMemories() async {
    final response = await dio.get('/memory/permanent');
    return response.data as List<dynamic>;
  }

  Future<List<dynamic>> getEpisodes() async {
    final response = await dio.get('/memory/episodes');
    return response.data as List<dynamic>;
  }

  Future<List<dynamic>> getGoals() async {
    final response = await dio.get('/memory/goals');
    return response.data as List<dynamic>;
  }

  Future<Map<String, dynamic>> createGoal(String title, String? description) async {
    final response = await dio.post('/memory/goals', data: {
      'title': title,
      'description': description,
    });
    return response.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getPersona() async {
    try {
      final response = await dio.get('/persona/state');
      return response.data as Map<String, dynamic>;
    } catch (_) {
      return {};
    }
  }

  // Privacy: Two-Phase /forget-me compliance
  Future<Map<String, dynamic>> forgetMe() async {
    final response = await dio.post('/memory/forget-me');
    await logout();
    return response.data as Map<String, dynamic>;
  }
}

final apiClient = ApiClient();
