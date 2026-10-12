import 'package:flutter/material.dart';

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFFFBF8FC),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              'CognAI',
              style: TextStyle(
                fontSize: 36,
                fontWeight: FontWeight.bold,
                letterSpacing: -0.5,
                color: Color(0xFF1B1B1E),
              ),
            ),
            SizedBox(height: 8),
            Text(
              'A Research-Grounded Cognitive Companion',
              style: TextStyle(
                fontSize: 14,
                color: Color(0xFF71787F),
              ),
            ),
            SizedBox(height: 32),
            SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(
                strokeWidth: 2.5,
                color: Color(0xFF075985),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
