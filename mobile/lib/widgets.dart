import 'package:flutter/material.dart';

import 'api.dart';
import 'state.dart';

/// A raised surface with a hard bottom edge, which gives the app its 3D look.
class Card3d extends StatelessWidget {
  const Card3d({super.key, required this.child, this.margin, this.padding = 14});

  final Widget child;
  final EdgeInsets? margin;
  final double padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: margin,
      padding: EdgeInsets.all(padding),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Colors.white, Color(0xFFF1F5EE)],
        ),
        borderRadius: BorderRadius.circular(16),
        boxShadow: const [
          BoxShadow(color: Color(0xFFD9D6C8), offset: Offset(0, 5)),
          BoxShadow(color: Color(0x2214532D), offset: Offset(0, 12), blurRadius: 20),
        ],
      ),
      child: child,
    );
  }
}

/// Stays on screen on every tab, so the shopper always sees what's left.
class BudgetBar extends StatelessWidget {
  const BudgetBar({super.key});

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final budget = state.budget;
    final left = budget == null ? 0.0 : budget - state.spent;
    final used = budget == null ? 0.0 : (state.spent / budget).clamp(0.0, 1.0);
    final over = budget != null && left < 0;
    final color = over
        ? const Color(0xFFB3361C)
        : used >= 0.8
            ? const Color(0xFFE39A1C)
            : const Color(0xFF1C7A43);
    return Card3d(
      margin: const EdgeInsets.fromLTRB(10, 6, 10, 8),
      padding: 10,
      child: Row(children: [
        SizedBox(
          width: 118,
          child: TextFormField(
            initialValue: budget?.toStringAsFixed(0) ?? '',
            key: ValueKey(state.budgetLoaded),
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'My budget', prefixText: '₱', isDense: true, border: OutlineInputBorder()),
            onChanged: (value) => state.setBudget(double.tryParse(value)),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            Text(
              budget == null
                  ? 'List total: ${peso(state.spent)}'
                  : over
                      ? '${peso(-left)} over budget'
                      : '${peso(left)} left of ${peso(budget)}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontWeight: FontWeight.w700, color: over ? color : null),
            ),
            if (budget != null) ...[
              const SizedBox(height: 5),
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: LinearProgressIndicator(value: used, minHeight: 9, color: color, backgroundColor: const Color(0xFFE8E6DC)),
              ),
            ],
          ]),
        ),
      ]),
    );
  }
}

/// Banner with real prices on cards tilted in perspective.
class HeroHeader extends StatelessWidget {
  const HeroHeader({super.key, required this.rows});

  final List<PriceRow>? rows;

  @override
  Widget build(BuildContext context) {
    final picks = (rows ?? const <PriceRow>[]).where((r) => r.isSrp).take(1).toList()
      ..addAll((rows ?? const <PriceRow>[]).where((r) => !r.isSrp).take(1));
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0C2F1B), Color(0xFF1C7A43)],
        ),
        borderRadius: BorderRadius.vertical(bottom: Radius.circular(24)),
        boxShadow: [
          BoxShadow(color: Color(0xFF0A2D18), offset: Offset(0, 5)),
          BoxShadow(color: Color(0x4414532D), offset: Offset(0, 14), blurRadius: 20),
        ],
      ),
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Transform(
            alignment: Alignment.center,
            transform: Matrix4.identity()
              ..setEntry(3, 2, 0.002)
              ..rotateY(-0.35)
              ..rotateX(0.12),
            child: DecoratedBox(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                boxShadow: const [BoxShadow(color: Color(0x66000000), offset: Offset(0, 8), blurRadius: 14)],
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: Image.asset('assets/icon.png', width: 62, height: 62),
              ),
            ),
          ),
          const SizedBox(width: 14),
          const Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Know the fair price before you pay.',
                  style: TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w800, height: 1.1)),
              SizedBox(height: 4),
              Text('Official prices from the DTI and DA', style: TextStyle(color: Color(0xFFD3E8D9))),
            ]),
          ),
        ]),
        if (picks.isNotEmpty) ...[
          const SizedBox(height: 14),
          Row(children: [
            for (final (index, row) in picks.indexed)
              Expanded(
                child: Transform(
                  alignment: Alignment.center,
                  transform: Matrix4.identity()
                    ..setEntry(3, 2, 0.0012)
                    ..rotateX(0.14)
                    ..rotateY(index == 0 ? 0.2 : -0.2),
                  child: Card3d(
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    padding: 10,
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(row.commodity, maxLines: 1, overflow: TextOverflow.ellipsis),
                      Text(peso(row.price),
                          style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w800, color: Color(0xFF14532D))),
                    ]),
                  ),
                ),
              ),
          ]),
        ],
      ]),
    );
  }
}

/// Tips a card back in perspective while it is pressed.
class PressTilt extends StatefulWidget {
  const PressTilt({super.key, required this.child});

  final Widget child;

  @override
  State<PressTilt> createState() => _PressTiltState();
}

class _PressTiltState extends State<PressTilt> {
  bool _pressed = false;

  void _set(bool value) => setState(() => _pressed = value);

  @override
  Widget build(BuildContext context) {
    return Listener(
      onPointerDown: (_) => _set(true),
      onPointerUp: (_) => _set(false),
      onPointerCancel: (_) => _set(false),
      child: TweenAnimationBuilder<double>(
        tween: Tween(end: _pressed ? 1 : 0),
        duration: const Duration(milliseconds: 140),
        curve: Curves.easeOut,
        child: widget.child,
        builder: (_, value, child) => Transform(
          alignment: Alignment.center,
          transform: Matrix4.identity()
            ..setEntry(3, 2, 0.0014)
            ..rotateX(-0.16 * value)
            ..scaleByDouble(1 - 0.03 * value, 1 - 0.03 * value, 1, 1),
          child: child,
        ),
      ),
    );
  }
}

class PriceCard extends StatelessWidget {
  const PriceCard({super.key, required this.row, required this.onAdd});

  final PriceRow row;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    final change = row.change;
    return PressTilt(
      child: Card3d(
      padding: 12,
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(row.commodity,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w700)),
            if (row.specification.isNotEmpty)
              Text(row.specification,
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.bodySmall),
            const Spacer(),
            Text(row.isSrp ? 'Official SRP · ${row.region}' : '${row.region} market average',
                maxLines: 1, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.bodySmall),
          ]),
        ),
        const SizedBox(width: 8),
        Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Text(peso(row.price),
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: Color(0xFF14532D))),
          Text('per ${row.unit}', style: Theme.of(context).textTheme.bodySmall),
          if (change != null && change != 0)
            Text('${change > 0 ? '▲' : '▼'} ${peso(change.abs())}',
                style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: change > 0 ? const Color(0xFFB3361C) : const Color(0xFF0A7A0A))),
          const Spacer(),
          IconButton(
            tooltip: 'Add to draft',
            visualDensity: VisualDensity.compact,
            onPressed: onAdd,
            icon: const Icon(Icons.playlist_add),
          ),
        ]),
      ]),
      ),
    );
  }
}

class Message extends StatelessWidget {
  const Message({super.key, required this.text, this.action, this.onAction});

  final String text;
  final String? action;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(children: [
        Text(text, textAlign: TextAlign.center),
        if (action != null) TextButton(onPressed: onAction, child: Text(action!)),
      ]),
    );
  }
}
