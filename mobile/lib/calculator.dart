import 'package:flutter/material.dart';

class CalculatorResult {
  CalculatorResult(this.name, this.amount);
  final String name;
  final double amount;
}

/// Keeps the arithmetic apart from the screen so it can be tested on its own.
class CalculatorEngine {
  String entry = '0';
  double? stored;
  String? operation;
  bool fresh = true;

  static double _apply(double a, double b, String op) => switch (op) {
        '+' => a + b,
        '-' => a - b,
        '×' => a * b,
        _ => b == 0 ? double.nan : a / b,
      };

  static String _tidy(double value) {
    if (!value.isFinite) return 'Error';
    final rounded = (value * 100).round() / 100;
    return rounded == rounded.truncateToDouble() ? rounded.toInt().toString() : rounded.toString();
  }

  double get value => double.tryParse(entry) ?? double.nan;

  void press(String key) {
    if (key == '=' || '+-×÷'.contains(key)) {
      final current = value;
      final result = stored != null && operation != null && !fresh ? _apply(stored!, current, operation!) : current;
      entry = _tidy(result);
      stored = key == '=' || !result.isFinite ? null : result;
      operation = key == '=' ? null : key;
      fresh = true;
      return;
    }
    if (key == '.' && !fresh && entry.contains('.')) return;
    if (fresh) {
      entry = key == '.' ? '0.' : key;
    } else {
      entry = entry == '0' && key != '.' ? key : entry + key;
    }
    fresh = false;
  }

  void backspace() => entry = entry.length > 1 ? entry.substring(0, entry.length - 1) : '0';

  void clear() {
    entry = '0';
    stored = null;
    operation = null;
    fresh = true;
  }
}

class CalculatorSheet extends StatefulWidget {
  const CalculatorSheet({super.key});

  @override
  State<CalculatorSheet> createState() => _CalculatorSheetState();
}

class _CalculatorSheetState extends State<CalculatorSheet> {
  static const _keys = ['7', '8', '9', '÷', '4', '5', '6', '×', '1', '2', '3', '-', '0', '.', '=', '+'];
  final _engine = CalculatorEngine();
  final _name = TextEditingController();

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  void _tap(VoidCallback action) => setState(action);

  @override
  Widget build(BuildContext context) {
    final canAdd = _name.text.trim().isNotEmpty && _engine.value.isFinite && _engine.value > 0;
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: const BoxDecoration(
          gradient: LinearGradient(colors: [Color(0xFF1E3A2A), Color(0xFF0E2418)]),
          borderRadius: BorderRadius.vertical(top: Radius.circular(22)),
        ),
        child: SafeArea(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: const Color(0xFFDFEEE0), borderRadius: BorderRadius.circular(10)),
              alignment: Alignment.centerRight,
              child: Text(_engine.entry, style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w700)),
            ),
            const SizedBox(height: 10),
            GridView.count(
              crossAxisCount: 4,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              mainAxisSpacing: 7,
              crossAxisSpacing: 7,
              childAspectRatio: 1.7,
              children: [
                for (final key in _keys) _Key(label: key, operation: '+-×÷='.contains(key), onTap: () => _tap(() => _engine.press(key))),
              ],
            ),
            const SizedBox(height: 7),
            Row(children: [
              Expanded(child: TextButton(onPressed: () => _tap(_engine.clear), child: const Text('Clear', style: TextStyle(color: Colors.white)))),
              Expanded(child: TextButton(onPressed: () => _tap(_engine.backspace), child: const Text('Delete', style: TextStyle(color: Colors.white)))),
            ]),
            TextField(
              controller: _name,
              onChanged: (_) => setState(() {}),
              style: const TextStyle(color: Colors.white),
              decoration: const InputDecoration(hintText: 'Item name', hintStyle: TextStyle(color: Color(0xFFB7CBBC))),
            ),
            const SizedBox(height: 8),
            FilledButton(
              onPressed: canAdd ? () => Navigator.pop(context, CalculatorResult(_name.text.trim(), _engine.value)) : null,
              child: const Text('Add to receipt'),
            ),
          ]),
        ),
      ),
    );
  }
}

class _Key extends StatelessWidget {
  const _Key({required this.label, required this.operation, required this.onTap});

  final String label;
  final bool operation;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: operation ? const Color(0xFFF2A93B) : Colors.white,
      borderRadius: BorderRadius.circular(10),
      elevation: 3,
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: onTap,
        child: Center(child: Text(label, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700))),
      ),
    );
  }
}
