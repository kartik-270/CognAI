import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:markdown/markdown.dart' as md;

/// Matches display math: $$ ... $$
class LatexBlockSyntax extends md.InlineSyntax {
  LatexBlockSyntax() : super(r'(?<!\\)\$\$([\s\S]+?)(?<!\\)\$\$');

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    final content = match.group(1);
    if (content == null || content.trim().isEmpty) return false;
    final el = md.Element('latex_block', [md.Text(content.trim())]);
    parser.addNode(el);
    return true;
  }
}

/// Matches display math: \[ ... \]
class LatexDisplayBracketSyntax extends md.InlineSyntax {
  LatexDisplayBracketSyntax() : super(r'\\\[([\s\S]+?)\\\]');

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    final content = match.group(1);
    if (content == null || content.trim().isEmpty) return false;
    final el = md.Element('latex_block', [md.Text(content.trim())]);
    parser.addNode(el);
    return true;
  }
}

/// Matches inline math: \( ... \)
class LatexInlineBracketSyntax extends md.InlineSyntax {
  LatexInlineBracketSyntax() : super(r'\\\(([\s\S]+?)\\\)');

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    final content = match.group(1);
    if (content == null || content.trim().isEmpty) return false;
    final el = md.Element('latex_inline', [md.Text(content.trim())]);
    parser.addNode(el);
    return true;
  }
}

/// Matches inline math: $ ... $
class LatexInlineSyntax extends md.InlineSyntax {
  LatexInlineSyntax() : super(r'(?<![\$\\])\$(?!\$)((?:[^\$])+?)(?<![\$\\])\$(?!\$)');

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    final content = match.group(1);
    if (content == null || content.trim().isEmpty) return false;
    final trimmed = content.trim();

    // Prevent matching currency text like "$10 and $20"
    if (_isLikelyCurrencyOrText(trimmed)) {
      return false;
    }

    final el = md.Element('latex_inline', [md.Text(trimmed)]);
    parser.addNode(el);
    return true;
  }

  static bool _isLikelyCurrencyOrText(String text) {
    // If it contains LaTeX math symbols, it's definitely math
    final hasMathSymbols = RegExp(r'(\\[a-zA-Z]+|[_^{}=+><\-\*]|\\cdot|\\approx|\\lambda|\\alpha)').hasMatch(text);
    if (hasMathSymbols) return false;

    // If it starts with digits and has spaces/regular words (e.g., "10 for lunch and 20")
    if (RegExp(r'^\d+(\.\d+)?\s+[a-zA-Z]').hasMatch(text)) {
      return true;
    }

    // Pure numbers without symbols are likely currency if matched across plain text
    if (RegExp(r'^\d+(\.\d+)?$').hasMatch(text)) {
      return true;
    }

    return false;
  }
}

class LatexElementBuilder extends MarkdownElementBuilder {
  final bool isDisplay;
  final TextStyle? textStyle;

  LatexElementBuilder({this.isDisplay = false, this.textStyle});

  @override
  Widget visitElementAfter(md.Element element, TextStyle? preferredStyle) {
    final rawTex = element.textContent.trim();
    // Normalize newlines inside formula into spaces, preserving escaped commands:
    final tex = rawTex.replaceAll(RegExp(r'\r?\n'), ' ').replaceAll(RegExp(r'\s+'), ' ');
    final style = preferredStyle ?? textStyle ?? const TextStyle(
      color: Color(0xFF1B1B1E),
      fontSize: 15,
      height: 1.4,
    );

    try {
      if (isDisplay) {
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 6.0),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Math.tex(
              tex,
              textStyle: style.copyWith(fontSize: (style.fontSize ?? 15) * 1.05),
              mathStyle: MathStyle.display,
              onErrorFallback: (err) => Text('\$\$$rawTex\$\$', style: style),
            ),
          ),
        );
      } else {
        return Math.tex(
          tex,
          textStyle: style,
          mathStyle: MathStyle.text,
          onErrorFallback: (err) => Text('\$$rawTex\$', style: style),
        );
      }
    } catch (_) {
      return Text(
        isDisplay ? '\$\$$rawTex\$\$' : '\$$rawTex\$',
        style: style,
      );
    }
  }
}

class LatexMarkdown extends StatelessWidget {
  final String data;
  final TextStyle? textStyle;
  final MarkdownStyleSheet? styleSheet;
  final bool selectable;

  const LatexMarkdown({
    super.key,
    required this.data,
    this.textStyle,
    this.styleSheet,
    this.selectable = true,
  });

  @override
  Widget build(BuildContext context) {
    final effectiveStyleSheet = styleSheet ?? MarkdownStyleSheet(
      p: textStyle ?? const TextStyle(
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
      code: TextStyle(
        fontFamily: 'JetBrains Mono',
        fontSize: 13,
        color: const Color(0xFF075985),
        backgroundColor: Colors.black.withValues(alpha: 0.06),
      ),
      codeblockDecoration: BoxDecoration(
        color: const Color(0xFF1E1E24),
        borderRadius: BorderRadius.circular(8),
      ),
      codeblockPadding: const EdgeInsets.all(12),
      listBullet: const TextStyle(
        color: Color(0xFF1B1B1E),
        fontSize: 15,
      ),
    );

    return MarkdownBody(
      data: data,
      selectable: selectable,
      styleSheet: effectiveStyleSheet,
      extensionSet: md.ExtensionSet(
        [...md.ExtensionSet.gitHubFlavored.blockSyntaxes],
        [
          LatexDisplayBracketSyntax(),
          LatexBlockSyntax(),
          LatexInlineBracketSyntax(),
          LatexInlineSyntax(),
          ...md.ExtensionSet.gitHubFlavored.inlineSyntaxes,
        ],
      ),
      builders: {
        'latex_block': LatexElementBuilder(isDisplay: true, textStyle: textStyle),
        'latex_inline': LatexElementBuilder(isDisplay: false, textStyle: textStyle),
      },
    );
  }
}
