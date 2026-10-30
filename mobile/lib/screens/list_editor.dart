import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../calculator.dart';
import '../drafts.dart';
import '../receipt.dart';
import '../state.dart';

/// Shared by My list and Drafts. The receipt follows the list, with no button to press.
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
  Timer? _debounce;
  Basket? _basket;
  String? _error;

  Draft get _draft => widget.draft;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _schedule();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _input.dispose();
    super.dispose();
  }

  void _changed() {
    setState(() {});
    widget.onChanged();
    _schedule();
  }

  void _schedule() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), _total);
  }

  void _add() {
    final items = parseItems(_input.text);
    if (items.isEmpty) return;
    items.forEach(_draft.add);
    _input.clear();
    _changed();
  }

  Future<void> _total() async {
    if (!mounted) return;
    final state = AppScope.of(context);
    if (_draft.items.isEmpty) {
      setState(() => _basket = null);
      state.setSpent(0);
      return;
    }
    try {
      final basket = await state.api.basket(
        _draft.items
            .map((i) => {
                  'query': i.query,
                  'quantity': i.quantity,
                  'price_id': i.priceId,
                  'custom_price': i.customPrice,
                })
            .toList(),
        island: state.city?.island,
      );
      if (!mounted) return;
      setState(() {
        _basket = basket;
        _error = null;
      });
      state.setSpent(basket.total);
      if (_draft.lastTotal != basket.total) {
        _draft.lastTotal = basket.total;
        widget.onChanged();
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  BasketLine? _lineFor(DraftItem item) {
    for (final line in _basket?.lines ?? const <BasketLine>[]) {
      if (line.query == item.query) return line;
    }
    return null;
  }

  void _pick(DraftItem item, Candidate candidate) {
    item
      ..priceId = candidate.id
      ..label = candidate.label
      ..customPrice = null;
    _changed();
  }

  Future<void> _openCalculator() async {
    final added = await showModalBottomSheet<CalculatorResult>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const CalculatorSheet(),
    );
    if (added == null) return;
    _draft.add(DraftItem(query: added.name, customPrice: added.amount));
    _changed();
  }

  @override
  Widget build(BuildContext context) {
    final basket = _basket;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      TextField(
        controller: _input,
        minLines: 1,
        maxLines: 4,
        decoration: InputDecoration(
          hintText: 'piatos, 2 x tilapia, mega sardines',
          border: const OutlineInputBorder(),
          suffixIcon: IconButton(
            tooltip: 'Add',
            onPressed: _draft.items.length >= maxItems ? null : _add,
            icon: const Icon(Icons.add_circle),
          ),
        ),
      ),
      const SizedBox(height: 6),
      for (final item in _draft.items) _ItemRow(item: item, line: _lineFor(item), onChanged: _changed, onPick: _pick, onRemove: () {
        _draft.items.remove(item);
        _changed();
      }),
      if (widget.footer != null && _draft.items.isNotEmpty) widget.footer!,
      if (_error != null)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ),
      const SizedBox(height: 14),
      ReceiptCard(draft: _draft, basket: basket),
      const SizedBox(height: 12),
      OutlinedButton.icon(
        onPressed: _openCalculator,
        icon: const Icon(Icons.calculate_outlined),
        label: const Text('Open calculator'),
      ),
    ]);
  }
}

class _ItemRow extends StatelessWidget {
  const _ItemRow({
    required this.item,
    required this.line,
    required this.onChanged,
    required this.onPick,
    required this.onRemove,
  });

  final DraftItem item;
  final BasketLine? line;
  final VoidCallback onChanged;
  final void Function(DraftItem, Candidate) onPick;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final current = line;
    final askPrice = item.customPrice != null ||
        current?.status == 'needs_price' ||
        current?.status == 'no_match';
    final note = switch (current?.status) {
      'matched' => '${peso(current!.unitPrice)} per ${current.selected!.unit}',
      'needs_price' => 'No official price. Enter the shelf price.',
      'no_match' => 'Not in our lists. Enter a price to count it.',
      'custom' => 'Your shelf price',
      _ => null,
    };
    final struck = item.checked ? TextDecoration.lineThrough : null;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(children: [
        Checkbox(
          value: item.checked,
          onChanged: (value) {
            item.checked = value ?? false;
            onChanged();
          },
        ),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(current?.status == 'custom' ? item.query : current?.label ?? item.query,
                style: TextStyle(fontWeight: FontWeight.w600, decoration: struck)),
            if (note != null) Text(note, style: Theme.of(context).textTheme.bodySmall),
          ]),
        ),
        if (askPrice)
          SizedBox(
            width: 82,
            child: TextFormField(
              key: ValueKey('price-${item.id}'),
              initialValue: item.customPrice?.toString() ?? '',
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(prefixText: '₱', hintText: 'Price', isDense: true, border: OutlineInputBorder()),
              onChanged: (value) {
                item.customPrice = double.tryParse(value);
                onChanged();
              },
            ),
          ),
        if (current != null && current.status == 'matched' && current.candidates.length > 1)
          PopupMenuButton<Candidate>(
            tooltip: 'Change item',
            onSelected: (candidate) => onPick(item, candidate),
            itemBuilder: (_) => [
              for (final c in current.candidates)
                PopupMenuItem(value: c, child: Text('${c.label} (${peso(c.price)})')),
            ],
          ),
        IconButton(
          tooltip: 'Fewer',
          visualDensity: VisualDensity.compact,
          onPressed: item.quantity <= 1
              ? null
              : () {
                  item.quantity--;
                  onChanged();
                },
          icon: const Icon(Icons.remove_circle_outline),
        ),
        Text('${item.quantity}'),
        IconButton(
          tooltip: 'More',
          visualDensity: VisualDensity.compact,
          onPressed: item.quantity >= 999
              ? null
              : () {
                  item.quantity++;
                  onChanged();
                },
          icon: const Icon(Icons.add_circle_outline),
        ),
        IconButton(
          tooltip: 'Remove',
          visualDensity: VisualDensity.compact,
          onPressed: onRemove,
          icon: const Icon(Icons.close),
        ),
      ]),
    );
  }
}
