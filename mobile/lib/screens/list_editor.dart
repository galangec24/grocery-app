import 'package:flutter/material.dart';

import '../api.dart';
import '../drafts.dart';
import '../state.dart';
import '../widgets.dart';

/// Shared by Multi search and Drafts: edit a list, then total it at official prices.
class ListEditor extends StatefulWidget {
  const ListEditor({super.key, required this.draft, required this.onChanged, this.footer});

  final Draft draft;
  final VoidCallback onChanged;
  final Widget? footer;

  @override
  State<ListEditor> createState() => _ListEditorState();
}

class _ListEditorState extends State<ListEditor> {
  final _input = TextEditingController();
  Basket? _basket;
  String? _error;
  bool _busy = false;

  Draft get _draft => widget.draft;

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  void _changed() {
    setState(() => _basket = null);
    widget.onChanged();
  }

  void _add() {
    final items = parseItems(_input.text);
    if (items.isEmpty) return;
    items.forEach(_draft.add);
    _input.clear();
    _changed();
  }

  Future<void> _total() async {
    final state = AppScope.of(context);
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final basket = await state.api.basket(
        _draft.items
            .map((i) => {'query': i.query, 'quantity': i.quantity, 'price_id': i.priceId})
            .toList(),
        island: state.city?.island,
      );
      if (mounted) setState(() => _basket = basket);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
    if (mounted) setState(() => _busy = false);
  }

  void _pick(BasketLine line, Candidate candidate) {
    final item = _draft.items.firstWhere((i) => i.query == line.query);
    item.priceId = candidate.id;
    item.label = candidate.label;
    widget.onChanged();
    _total();
  }

  @override
  Widget build(BuildContext context) {
    final count = _draft.items.length;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      TextField(
        controller: _input,
        minLines: 1,
        maxLines: 4,
        decoration: InputDecoration(
          hintText: 'bear brand\n2 x tilapia\neggs, sardines',
          border: const OutlineInputBorder(),
          suffixIcon: IconButton(
            tooltip: 'Add',
            onPressed: count >= maxItems ? null : _add,
            icon: const Icon(Icons.add_circle),
          ),
        ),
      ),
      for (final item in _draft.items)
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(item.query),
          subtitle: item.label != null && item.label != item.query ? Text(item.label!) : null,
          trailing: Row(mainAxisSize: MainAxisSize.min, children: [
            IconButton(
              tooltip: 'Fewer',
              onPressed: item.quantity <= 1
                  ? null
                  : () {
                      item.quantity--;
                      _changed();
                    },
              icon: const Icon(Icons.remove_circle_outline),
            ),
            Text('${item.quantity}'),
            IconButton(
              tooltip: 'More',
              onPressed: item.quantity >= 999
                  ? null
                  : () {
                      item.quantity++;
                      _changed();
                    },
              icon: const Icon(Icons.add_circle_outline),
            ),
            IconButton(
              tooltip: 'Remove',
              onPressed: () {
                _draft.items.remove(item);
                _changed();
              },
              icon: const Icon(Icons.close),
            ),
          ]),
        ),
      if (count > 0) ...[
        const SizedBox(height: 8),
        FilledButton(
          onPressed: _busy ? null : _total,
          child: Text(_busy ? 'Totalling…' : 'Total $count ${count == 1 ? 'item' : 'items'}'),
        ),
      ],
      if (widget.footer != null && count > 0) widget.footer!,
      if (_error != null)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ),
      if (_basket != null) _BasketView(basket: _basket!, onPick: _pick),
    ]);
  }
}

class _BasketView extends StatelessWidget {
  const _BasketView({required this.basket, required this.onPick});

  final Basket basket;
  final void Function(BasketLine, Candidate) onPick;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Card3d(
          child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Flexible(child: Text('Estimated total at official prices\n${basket.itemsMatched} of ${basket.lines.length} items found')),
            Text(peso(basket.total),
                style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: Color(0xFF14532D))),
          ]),
        ),
        const SizedBox(height: 8),
        for (final line in basket.lines)
          if (!line.matched)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.warning_amber),
              title: Text(line.query),
              subtitle: const Text("Not in the official lists, so it isn't in the total."),
            )
          else
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(line.selected!.label),
              subtitle: Text('${peso(line.selected!.price)} per ${line.selected!.unit} × ${line.quantity}'),
              trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                Text(peso(line.lineTotal), style: const TextStyle(fontWeight: FontWeight.w700)),
                if (line.candidates.length > 1)
                  PopupMenuButton<Candidate>(
                    tooltip: 'Change item',
                    onSelected: (candidate) => onPick(line, candidate),
                    itemBuilder: (_) => [
                      for (final c in line.candidates)
                        PopupMenuItem(value: c, child: Text('${c.label} (${peso(c.price)})')),
                    ],
                  ),
              ]),
            ),
        Text('Market prices are Metro Manila averages per kilo or piece. Shelf prices may differ.',
            style: Theme.of(context).textTheme.bodySmall),
      ]),
    );
  }
}
