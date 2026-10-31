import 'package:flutter/material.dart';

import 'api.dart';
import 'drafts.dart';
import 'state.dart';

const _mono = TextStyle(fontFamily: 'monospace', fontSize: 12.5, color: Color(0xFF23231F));

/// A paper till receipt with a torn bottom edge.
class ReceiptCard extends StatelessWidget {
  const ReceiptCard({super.key, required this.draft, required this.basket});

  final Draft draft;
  final Basket? basket;

  @override
  Widget build(BuildContext context) {
    final budget = AppScope.of(context).budget;
    final lines = basket?.lines ?? const <BasketLine>[];
    final counted = lines.where((l) => l.lineTotal > 0).toList();
    final waiting = lines.where((l) => l.status == 'needs_price' || l.status == 'no_match').toList();
    final total = basket?.total ?? 0;
    final left = budget == null ? null : budget - total;
    final ticked = draft.items.where((i) => i.checked).map((i) => i.query).toSet();
    final inCart = lines.where((l) => ticked.contains(l.query)).fold<double>(0, (sum, l) => sum + l.lineTotal);

    return Transform(
      alignment: Alignment.center,
      transform: Matrix4.identity()
        ..setEntry(3, 2, 0.0008)
        ..rotateX(0.03)
        ..rotateZ(-0.006),
      child: DecoratedBox(
        decoration: const BoxDecoration(
          boxShadow: [BoxShadow(color: Color(0x33282814), offset: Offset(0, 12), blurRadius: 22)],
        ),
        child: ClipPath(
          clipper: _TornEdge(),
          child: Container(
            color: const Color(0xFFFFFDF6),
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 26),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const Text('GROCERY PRICE FINDER',
                  textAlign: TextAlign.center, style: TextStyle(fontFamily: 'monospace', fontWeight: FontWeight.w800)),
              Text(draft.name.isEmpty ? 'Shopping list' : draft.name, textAlign: TextAlign.center, style: _mono),
              const _Rule(),
              if (lines.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 14),
                  child: Text('Your items will print here.', textAlign: TextAlign.center, style: _mono),
                ),
              for (final line in counted)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    Text(line.status == 'custom' ? line.query : line.label,
                        style: _mono.copyWith(fontWeight: FontWeight.w700)),
                    _Row('${line.quantity} x ${line.unitPrice.toStringAsFixed(2)}${line.status == 'custom' ? ' *' : line.status == 'reported' ? ' †' : line.status == 'estimated' ? ' ≈' : ''}',
                        line.lineTotal.toStringAsFixed(2)),
                  ]),
                ),
              if (waiting.isNotEmpty) const _Rule(),
              for (final line in waiting) _Row(line.label, 'needs price'),
              if (lines.isNotEmpty) ...[
                const _Rule(),
                _Row('TOTAL', peso(total), bold: true),
                if (ticked.isNotEmpty) _Row('IN CART', peso(inCart)),
                if (budget != null) _Row('BUDGET', peso(budget)),
                if (left != null) _Row(left < 0 ? 'OVER BY' : 'LEFT', peso(left.abs()), alert: left < 0),
                const _Rule(),
                const Text('* Your shelf price. † Reported store price. ≈ Estimate from similar items. Others are official. All may differ at checkout.',
                    style: TextStyle(fontFamily: 'monospace', fontSize: 10.5, color: Color(0xFF68665C))),
              ],
            ]),
          ),
        ),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row(this.left, this.right, {this.bold = false, this.alert = false});

  final String left;
  final String right;
  final bool bold;
  final bool alert;

  @override
  Widget build(BuildContext context) {
    final style = _mono.copyWith(
      fontWeight: bold || alert ? FontWeight.w800 : FontWeight.w400,
      fontSize: bold ? 15 : 12.5,
      color: alert ? const Color(0xFFA82424) : null,
    );
    return Row(children: [
      Expanded(child: Text(left, style: style)),
      Text(right, style: style),
    ]);
  }
}

class _Rule extends StatelessWidget {
  const _Rule();

  @override
  Widget build(BuildContext context) => const Padding(
        padding: EdgeInsets.symmetric(vertical: 6),
        child: Text('- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -',
            maxLines: 1, overflow: TextOverflow.clip, softWrap: false, style: TextStyle(color: Color(0xFF8E8C80))),
      );
}

class _TornEdge extends CustomClipper<Path> {
  @override
  Path getClip(Size size) {
    const tooth = 14.0;
    final path = Path()
      ..lineTo(size.width, 0)
      ..lineTo(size.width, size.height);
    var x = size.width;
    while (x > 0) {
      path
        ..lineTo(x - tooth / 2, size.height - tooth / 2)
        ..lineTo(x - tooth, size.height);
      x -= tooth;
    }
    return path..close();
  }

  @override
  bool shouldReclip(_TornEdge oldClipper) => false;
}
