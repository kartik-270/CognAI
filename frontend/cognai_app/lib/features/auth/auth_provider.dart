import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_sign_in/google_sign_in.dart';
import '../../core/network/api_client.dart';

enum AuthFlowStep {
  login,
  registerStep1,
  registerStep2,
  registerOtp,
  forgotPasswordEmail,
  forgotPasswordReset,
}

class AuthState {
  final bool isLoading;
  final bool isAuthenticated;
  final bool isCheckingAuth;
  final String? errorMessage;
  final AuthFlowStep currentStep;
  final String? registeredEmail; // Persisted across steps

  const AuthState({
    this.isLoading = false,
    this.isAuthenticated = false,
    this.isCheckingAuth = true,
    this.errorMessage,
    this.currentStep = AuthFlowStep.login,
    this.registeredEmail,
  });

  AuthState copyWith({
    bool? isLoading,
    bool? isAuthenticated,
    bool? isCheckingAuth,
    String? errorMessage,
    AuthFlowStep? currentStep,
    String? registeredEmail,
  }) {
    return AuthState(
      isLoading: isLoading ?? this.isLoading,
      isAuthenticated: isAuthenticated ?? this.isAuthenticated,
      isCheckingAuth: isCheckingAuth ?? this.isCheckingAuth,
      errorMessage: errorMessage,
      currentStep: currentStep ?? this.currentStep,
      registeredEmail: registeredEmail ?? this.registeredEmail,
    );
  }
}

class AuthNotifier extends StateNotifier<AuthState> {
  final ApiClient _apiClient;

  AuthNotifier(this._apiClient) : super(const AuthState(isCheckingAuth: true)) {
    checkAuthStatus();
  }

  void setFlowStep(AuthFlowStep step) {
    state = state.copyWith(currentStep: step, errorMessage: null);
  }

  Future<void> checkAuthStatus() async {
    try {
      final hasToken = await _apiClient.hasToken();
      state = state.copyWith(
        isAuthenticated: hasToken,
        isCheckingAuth: false,
      );
    } catch (_) {
      state = state.copyWith(
        isAuthenticated: false,
        isCheckingAuth: false,
      );
    }
  }

  Future<bool> login(String email, String password) async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      await _apiClient.login(email, password);
      state = state.copyWith(isLoading: false, isAuthenticated: true);
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Login failed. Please check your credentials.',
      );
      return false;
    }
  }

  Future<bool> submitRegisterStep1(String email) async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      await _apiClient.registerStep1(email);
      state = state.copyWith(
        isLoading: false,
        currentStep: AuthFlowStep.registerStep2,
        registeredEmail: email,
      );
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Failed to initiate registration. Email may be in use.',
      );
      return false;
    }
  }

  Future<bool> submitRegisterStep2(String password, String confirmPassword) async {
    final email = state.registeredEmail;
    if (email == null) return false;

    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      await _apiClient.registerStep2(email, password, confirmPassword);
      state = state.copyWith(
        isLoading: false,
        currentStep: AuthFlowStep.registerOtp,
      );
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Failed to set password. Make sure they match.',
      );
      return false;
    }
  }

  Future<bool> submitVerifyOtp(String otp) async {
    final email = state.registeredEmail;
    if (email == null) return false;

    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      await _apiClient.verifyOtp(email, otp);
      state = state.copyWith(isLoading: false);
      return true; // We don't auto-login here since no token is returned, or they can route to login.
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Invalid or expired OTP.',
      );
      return false;
    }
  }

  Future<bool> submitResendRegisterOtp() async {
    final email = state.registeredEmail;
    if (email == null) return false;

    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      await _apiClient.resendRegisterOtp(email);
      state = state.copyWith(isLoading: false);
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Failed to resend OTP.',
      );
      return false;
    }
  }

  Future<bool> submitForgotPasswordEmail(String email) async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      await _apiClient.forgotPassword(email);
      state = state.copyWith(
        isLoading: false,
        currentStep: AuthFlowStep.forgotPasswordReset,
        registeredEmail: email,
      );
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Failed to request password reset.',
      );
      return false;
    }
  }

  Future<bool> submitForgotPasswordReset(String otp, String newPassword, String confirmPassword) async {
    final email = state.registeredEmail;
    if (email == null) return false;

    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      await _apiClient.resetPassword(email, otp, newPassword, confirmPassword);
      state = state.copyWith(
        isLoading: false,
        currentStep: AuthFlowStep.login, // Go back to login after reset
      );
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Failed to reset password. Check OTP and passwords.',
      );
      return false;
    }
  }

  Future<void> logout() async {
    await _apiClient.logout();
    state = const AuthState(isAuthenticated: false, isCheckingAuth: false);
  }

  Future<bool> signInWithGoogle({String? clientId}) async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      String? effectiveClientId = clientId ?? configuredGoogleClientId;
      if (effectiveClientId == null || effectiveClientId.isEmpty) {
        effectiveClientId = await _apiClient.fetchRemoteGoogleClientId();
      }

      final GoogleSignIn googleSignIn = GoogleSignIn(
        clientId: effectiveClientId,
        scopes: ['email', 'profile'],
      );

      final GoogleSignInAccount? account = await googleSignIn.signIn();
      if (account == null) {
        state = state.copyWith(isLoading: false);
        return false;
      }

      final GoogleSignInAuthentication auth = await account.authentication;
      await _apiClient.loginWithGoogleToken(
        idToken: auth.idToken,
        accessToken: auth.accessToken,
      );

      state = state.copyWith(isLoading: false, isAuthenticated: true);
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Google Sign-In failed: ${e.toString()}',
      );
      return false;
    }
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  return AuthNotifier(apiClient);
});
