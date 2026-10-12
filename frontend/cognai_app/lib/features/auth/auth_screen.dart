import 'package:flutter/material.dart';
import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'auth_provider.dart';
import 'package:go_router/go_router.dart';

class AuthScreen extends ConsumerStatefulWidget {
  const AuthScreen({super.key});

  @override
  ConsumerState<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends ConsumerState<AuthScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  final _otpController = TextEditingController();
  
  Timer? _resendTimer;
  int _resendSeconds = 60;

  @override
  void initState() {
    super.initState();
  }

  void _startResendTimer() {
    setState(() {
      _resendSeconds = 60;
    });
    _resendTimer?.cancel();
    _resendTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (_resendSeconds > 0) {
        setState(() {
          _resendSeconds--;
        });
      } else {
        timer.cancel();
      }
    });
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _otpController.dispose();
    _resendTimer?.cancel();
    super.dispose();
  }

  void _showError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.red.shade700),
    );
  }

  void _showSuccess(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.green.shade700),
    );
  }

  Future<void> _submitLogin() async {
    final email = _emailController.text.trim();
    final password = _passwordController.text.trim();
    if (email.isEmpty || password.isEmpty) {
      _showError('Please enter both email and password.');
      return;
    }

    final notifier = ref.read(authProvider.notifier);
    final success = await notifier.login(email, password);
    if (!mounted) return;
    if (success) {
      context.go('/chat');
    } else {
      _showError(ref.read(authProvider).errorMessage ?? 'Login failed.');
    }
  }

  Future<void> _submitRegisterStep1() async {
    final email = _emailController.text.trim();
    if (email.isEmpty) {
      _showError('Please enter your email.');
      return;
    }
    final notifier = ref.read(authProvider.notifier);
    final success = await notifier.submitRegisterStep1(email);
    if (!success && mounted) {
      _showError(ref.read(authProvider).errorMessage ?? 'Error on step 1.');
    }
  }

  Future<void> _submitRegisterStep2() async {
    final password = _passwordController.text.trim();
    final confirm = _confirmPasswordController.text.trim();
    if (password.isEmpty || confirm.isEmpty) {
      _showError('Please fill both password fields.');
      return;
    }
    if (password != confirm) {
      _showError('Passwords do not match.');
      return;
    }
    final notifier = ref.read(authProvider.notifier);
    final success = await notifier.submitRegisterStep2(password, confirm);
    if (success && mounted) {
      _startResendTimer();
    } else if (!success && mounted) {
      _showError(ref.read(authProvider).errorMessage ?? 'Error on step 2.');
    }
  }

  Future<void> _submitRegisterOtp() async {
    final otp = _otpController.text.trim();
    if (otp.isEmpty) {
      _showError('Please enter the OTP sent to your email.');
      return;
    }
    final notifier = ref.read(authProvider.notifier);
    final success = await notifier.submitVerifyOtp(otp);
    if (success && mounted) {
      _showSuccess('Registration complete! Please login.');
      notifier.setFlowStep(AuthFlowStep.login);
    } else if (mounted) {
      _showError(ref.read(authProvider).errorMessage ?? 'Invalid OTP.');
    }
  }

  Future<void> _submitResendOtp() async {
    final notifier = ref.read(authProvider.notifier);
    final success = await notifier.submitResendRegisterOtp();
    if (success && mounted) {
      _showSuccess('OTP resent successfully.');
      _startResendTimer();
    } else if (mounted) {
      _showError(ref.read(authProvider).errorMessage ?? 'Failed to resend OTP.');
    }
  }

  Future<void> _submitForgotEmail() async {
    final email = _emailController.text.trim();
    if (email.isEmpty) {
      _showError('Please enter your email.');
      return;
    }
    final notifier = ref.read(authProvider.notifier);
    final success = await notifier.submitForgotPasswordEmail(email);
    if (success && mounted) {
      _showSuccess('OTP requested.');
    } else if (mounted) {
      _showError(ref.read(authProvider).errorMessage ?? 'Failed to request OTP.');
    }
  }

  Future<void> _submitForgotReset() async {
    final otp = _otpController.text.trim();
    final newPass = _passwordController.text.trim();
    final confirm = _confirmPasswordController.text.trim();

    if (otp.isEmpty || newPass.isEmpty || confirm.isEmpty) {
      _showError('Please fill all fields.');
      return;
    }
    if (newPass != confirm) {
      _showError('Passwords do not match.');
      return;
    }
    
    final notifier = ref.read(authProvider.notifier);
    final success = await notifier.submitForgotPasswordReset(otp, newPass, confirm);
    if (success && mounted) {
      _showSuccess('Password reset successfully. Please login.');
      // Clears fields for login
      _passwordController.clear();
      _confirmPasswordController.clear();
      _otpController.clear();
    } else if (mounted) {
      _showError(ref.read(authProvider).errorMessage ?? 'Reset failed.');
    }
  }

  Future<void> _googleSignIn() async {
    final notifier = ref.read(authProvider.notifier);
    final success = await notifier.signInWithGoogle();
    if (!mounted) return;
    if (success) {
      context.go('/chat');
    } else {
      final error = ref.read(authProvider).errorMessage;
      if (error != null) {
        _showError(error);
      }
    }
  }

  Widget _buildTextField(String label, TextEditingController controller, {bool obscure = false, String? hint}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(label, style: Theme.of(context).textTheme.labelSmall),
        const SizedBox(height: 8),
        TextField(
          controller: controller,
          obscureText: obscure,
          decoration: InputDecoration(hintText: hint),
        ),
        const SizedBox(height: 20),
      ],
    );
  }

  Widget _buildStepUI(AuthFlowStep step) {
    final notifier = ref.read(authProvider.notifier);
    final state = ref.watch(authProvider);

    switch (step) {
      case AuthFlowStep.login:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildTextField('EMAIL', _emailController, hint: 'name@example.com'),
            _buildTextField('PASSWORD', _passwordController, obscure: true, hint: '••••••••'),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () => notifier.setFlowStep(AuthFlowStep.forgotPasswordEmail),
                child: const Text('FORGOT PASSWORD?'),
              ),
            ),
            const SizedBox(height: 16),
            _buildSubmitButton('Sign In', _submitLogin, state.isLoading),
            const SizedBox(height: 16),
            _buildGoogleButton(),
            const SizedBox(height: 28),
            TextButton(
              onPressed: () => notifier.setFlowStep(AuthFlowStep.registerStep1),
              child: const Text("Don't have an account? Register"),
            ),
          ],
        );

      case AuthFlowStep.registerStep1:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Step 1: Enter your email to begin.'),
            const SizedBox(height: 20),
            _buildTextField('EMAIL', _emailController, hint: 'name@example.com'),
            _buildSubmitButton('Continue', _submitRegisterStep1, state.isLoading),
            const SizedBox(height: 16),
            TextButton(
              onPressed: () => notifier.setFlowStep(AuthFlowStep.login),
              child: const Text("Back to Login"),
            ),
          ],
        );

      case AuthFlowStep.registerStep2:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Step 2: Create a password for ${state.registeredEmail}.'),
            const SizedBox(height: 20),
            _buildTextField('PASSWORD', _passwordController, obscure: true, hint: '••••••••'),
            _buildTextField('CONFIRM PASSWORD', _confirmPasswordController, obscure: true, hint: '••••••••'),
            _buildSubmitButton('Continue', _submitRegisterStep2, state.isLoading),
            const SizedBox(height: 16),
            TextButton(
              onPressed: () => notifier.setFlowStep(AuthFlowStep.registerStep1),
              child: const Text("Back to Step 1"),
            ),
          ],
        );

      case AuthFlowStep.registerOtp:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Step 3: Enter the OTP sent to ${state.registeredEmail}.'),
            const SizedBox(height: 20),
            _buildTextField('OTP CODE', _otpController, hint: '123456'),
            _buildSubmitButton('Verify & Register', _submitRegisterOtp, state.isLoading),
            const SizedBox(height: 16),
            TextButton(
              onPressed: _resendSeconds > 0 || state.isLoading ? null : _submitResendOtp,
              child: Text(_resendSeconds > 0 ? "Resend OTP in $_resendSeconds s" : "Resend OTP"),
            ),
            TextButton(
              onPressed: () => notifier.setFlowStep(AuthFlowStep.registerStep1),
              child: const Text("Start Over"),
            ),
          ],
        );

      case AuthFlowStep.forgotPasswordEmail:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Reset Password: Enter your email to receive an OTP.'),
            const SizedBox(height: 20),
            _buildTextField('EMAIL', _emailController, hint: 'name@example.com'),
            _buildSubmitButton('Request OTP', _submitForgotEmail, state.isLoading),
            const SizedBox(height: 16),
            TextButton(
              onPressed: () => notifier.setFlowStep(AuthFlowStep.login),
              child: const Text("Back to Login"),
            ),
          ],
        );

      case AuthFlowStep.forgotPasswordReset:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Enter the OTP sent to ${state.registeredEmail} and your new password.'),
            const SizedBox(height: 20),
            _buildTextField('OTP CODE', _otpController, hint: '123456'),
            _buildTextField('NEW PASSWORD', _passwordController, obscure: true, hint: '••••••••'),
            _buildTextField('CONFIRM NEW PASSWORD', _confirmPasswordController, obscure: true, hint: '••••••••'),
            _buildSubmitButton('Reset Password', _submitForgotReset, state.isLoading),
            const SizedBox(height: 16),
            TextButton(
              onPressed: () => notifier.setFlowStep(AuthFlowStep.login),
              child: const Text("Cancel"),
            ),
          ],
        );
    }
  }

  Widget _buildSubmitButton(String label, VoidCallback onPressed, bool isLoading) {
    return ElevatedButton(
      onPressed: isLoading ? null : onPressed,
      style: ElevatedButton.styleFrom(
        padding: const EdgeInsets.symmetric(vertical: 16),
      ),
      child: isLoading
          ? const SizedBox(
              height: 20,
              width: 20,
              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
            )
          : Text(
              label,
              style: const TextStyle(fontFamily: 'Manrope', fontWeight: FontWeight.w600),
            ),
    );
  }

  Widget _buildGoogleButton() {
    return OutlinedButton.icon(
      onPressed: _googleSignIn,
      icon: const Icon(Icons.login),
      label: const Text(
        'Continue with Google', 
        style: TextStyle(fontFamily: 'Manrope', fontWeight: FontWeight.w600),
      ),
      style: OutlinedButton.styleFrom(
        padding: const EdgeInsets.symmetric(vertical: 16),
        foregroundColor: const Color(0xFF18181B),
        side: const BorderSide(color: Color(0xFFE4E4E7)),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
      ),
    );
  }

  String _getTitle(AuthFlowStep step) {
    switch (step) {
      case AuthFlowStep.login: return 'Sign In';
      case AuthFlowStep.registerStep1:
      case AuthFlowStep.registerStep2:
      case AuthFlowStep.registerOtp: return 'Create Account';
      case AuthFlowStep.forgotPasswordEmail:
      case AuthFlowStep.forgotPasswordReset: return 'Reset Password';
    }
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 40.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  _getTitle(authState.currentStep),
                  style: Theme.of(context).textTheme.displayLarge?.copyWith(fontSize: 32),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(
                  'CognAI: A Research-Grounded Cognitive Companion',
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                    color: const Color(0xFF71787F),
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 40),
                
                _buildStepUI(authState.currentStep),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
