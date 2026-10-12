import 'package:flutter/material.dart';

class CognAITheme {
  // Monochromatic Base
  static const Color surface = Color(0xFFFFFFFF); // Pure White surfaces
  static const Color secondarySurface = Color(0xFFF4F4F5);
  static const Color textHighContrast = Color(0xFF18181B);
  
  // Brand Primary
  static const Color primaryAccent = Color(0xFF075985);
  
  // Borders
  static const Color borderSubtle = Color(0xFFE4E4E7);

  static ThemeData get lightTheme {
    return ThemeData(
      scaffoldBackgroundColor: surface,
      primaryColor: primaryAccent,
      fontFamily: 'Inter', // Fallback, will be overridden by local fonts
      
      // Typography overrides based on DESIGN.md
      textTheme: const TextTheme(
        displayLarge: TextStyle(fontFamily: 'Manrope', color: textHighContrast, fontWeight: FontWeight.bold),
        bodyLarge: TextStyle(fontFamily: 'Inter', color: textHighContrast),
        labelSmall: TextStyle(fontFamily: 'JetBrains Mono', color: textHighContrast, letterSpacing: 1.2),
      ),
      
      // Nullifying default Material shadows
      appBarTheme: const AppBarTheme(
        backgroundColor: surface,
        elevation: 0,
        iconTheme: IconThemeData(color: textHighContrast),
      ),
      
      // Flat cards with 1px border
      cardTheme: CardThemeData(
        color: surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: const BorderSide(color: borderSubtle, width: 1),
        ),
      ),
      
      // Solid deep blue buttons
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primaryAccent,
          foregroundColor: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
        ),
      ),
      
      // 1px Bordered inputs, shifting to 2px Primary blue on focus
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(color: borderSubtle, width: 1),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(color: borderSubtle, width: 1),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(color: primaryAccent, width: 2),
        ),
      ),
    );
  }
}
