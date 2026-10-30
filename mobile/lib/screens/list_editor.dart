import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../best_store.dart';
import '../calculator.dart';
import '../drafts.dart';
import '../purchases.dart';
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
        city: state.city?.city,
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

  Future<void> _sharePrices() async {
    final state = AppScope.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final city = state.city;
    if (city == null || city.stores.isEmpty) {
      messenger.showSnackBar(const SnackBar(content: Text('Find your city on the Prices tab first.')));
      return;
    }
    final store = await showModalBottomSheet<CityStore>(
      context: context,
      builder: (context) => SafeArea(
        child: ListView(shrinkWrap: true, children: [
          const ListTile(title: Text('Where did you see these prices?'), subtitle: Text('Only the item, price and store are shared.')),
          for (final s in city.stores)
            ListTile(
              title: Text(s.name),
              subtitle: Text('${s.type} · ${s.distanceKm.toStringAsFixed(1)} km'),
              onTap: () => Navigator.pop(context, s),
            ),
        ]),
      ),
    );
    if (store == null) return;
    var shared = 0;
    for (final item in _draft.items.where((i) => (i.customPrice ?? 0) > 0)) {
      final held = await state.api.shareShelfPrice(
        name: _lineFor(item)?.label ?? item.query,
        store: store,
        city: city.city,
        price: item.customPrice!,
      );
      if (!held) shared++;
    }
    messenger.showSnackBar(SnackBar(content: Text('Thanks! $shared shared with shoppers in ${city.city}.')));
    _schedule();
  }

  Future<void> _savePurchase() async {
    final basket = _basket;
    if (basket == null) return;
    final messenger = ScaffoldMessenger.of(context);
    final date = await showDatePicker(
      context: context,
      initialDate: DateTime.now(),
      firstDate: DateTime(2020),
      lastDate: DateTime.now(),
      helpText: 'Date of purchase',
    );
    if (date == null) return;
    await PurchaseStore().save(Purchase(
      name: _draft.name.isEmpty ? 'Shopping trip' : _draft.name,
      date: date,
      total: basket.total,
      lines: [
        for (final line in basket.lines)
          if (line.lineTotal > 0)
            PurchaseLine(
              name: line.status == 'custom' ? line.query : line.label,
              quantity: line.quantity,
              unitPrice: line.unitPrice,
              lineTotal: line.lineTotal,
            ),
      ],
    ));
    messenger.showSnackBar(const SnackBar(content: Text('Saved to Reports')));
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
      const SizedBox(height: 14),
      BestStoreCard(queries: _draft.items.map((i) => i.query).toList()),
      const SizedBox(height: 12),
      if (_draft.items.any((i) => (i.customPrice ?? 0) > 0)) ...[
        OutlinedButton.icon(
          onPressed: _sharePrices,
          icon: const Icon(Icons.campaign_outlined),
          label: const Text('Share prices with other shoppers'),
        ),
        const SizedBox(height: 8),
      ],
      if (basket != null && basket.total > 0) ...[
        FilledButton.icon(
          onPressed: _savePurchase,
          icon: const Icon(Icons.bookmark_add_outlined),
          label: const Text('Save this purchase'),
        ),
        const SizedBox(height: 8),
      ],
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
        current?.status == 'reported' ||
        current?.status == 'needs_price' ||
        current?.status == 'no_match';
    final note = switch (current?.status) {
      'matched' => '${peso(current!.unitPrice)} per ${current.selected!.unit}',
      'reported' => 'Reported at ${current!.reportedStore}',
      'needs_price' => 'No price yet. Be the first to enter it.',
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
