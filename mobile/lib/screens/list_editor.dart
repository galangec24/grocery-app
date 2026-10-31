import 'dart:async';

import 'package:flutter/material.dart';

import 'package:image_picker/image_picker.dart';

import '../account.dart';
import '../api.dart';
import '../best_store.dart';
import '../calculator.dart';
import '../drafts.dart';
import '../purchases.dart';
import '../receipt.dart';
import '../state.dart';
import '../widgets.dart';

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
  Timer? _searchTimer;
  List<Suggestion> _suggestions = const [];
  Basket? _basket;
  int _liveVersion = -1;
  String? _error;

  Draft get _draft => widget.draft;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final version = AppScope.of(context).liveVersion;
    if (version != _liveVersion) {
      _liveVersion = version;
      _schedule();
    }
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchTimer?.cancel();
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
    _suggestions = const [];
    _changed();
  }

  void _search(String text) {
    _searchTimer?.cancel();
    if (text.trim().isEmpty) {
      setState(() => _suggestions = const []);
      return;
    }
    _searchTimer = Timer(const Duration(milliseconds: 250), () async {
      final state = AppScope.of(context);
      try {
        final found = await state.api.suggest(text.trim(), island: state.city?.island, city: state.city?.city);
        if (mounted && _input.text == text) setState(() => _suggestions = found);
      } on ApiException {
        if (mounted) setState(() => _suggestions = const []);
      }
    });
  }

  void _pickSuggestion(Suggestion item) {
    _draft.add(DraftItem(query: item.label, priceId: item.priceId, label: item.label));
    _input.clear();
    _suggestions = const [];
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
    var token = await state.accessToken();
    if (token == null) {
      if (!mounted || !await askToSignIn(context)) return;
      token = await state.accessToken();
      if (token == null) return;
    }
    if (!mounted) return;
    final store = await showModalBottomSheet<CityStore>(
      context: context,
      builder: (context) => SafeArea(
        child: ListView(shrinkWrap: true, children: [
          const ListTile(title: Text('Where did you see these prices?')),
          for (final s in city.stores)
            ListTile(
              title: Text(s.name),
              subtitle: Text('${s.type} · ${s.distanceKm.toStringAsFixed(1)} km'),
              onTap: () => Navigator.pop(context, s),
            ),
        ]),
      ),
    );
    if (store == null || !mounted) return;
    final source = await showModalBottomSheet<ImageSource?>(
      context: context,
      builder: (context) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const ListTile(
            title: Text('Add proof to get these verified'),
            subtitle: Text('Photograph the receipt or shelf tag. Cover card numbers and personal details. Only administrators see it.'),
          ),
          ListTile(leading: const Icon(Icons.photo_camera), title: const Text('Take a photo'), onTap: () => Navigator.pop(context, ImageSource.camera)),
          ListTile(leading: const Icon(Icons.photo_library), title: const Text('Choose a photo'), onTap: () => Navigator.pop(context, ImageSource.gallery)),
          ListTile(leading: const Icon(Icons.send), title: const Text('Share without proof'), onTap: () => Navigator.pop(context)),
        ]),
      ),
    );
    final shot = source == null ? null : await ImagePicker().pickImage(source: source, maxWidth: 1280, maxHeight: 1280, imageQuality: 72);
    final photo = await shot?.readAsBytes();
    var sent = 0;
    try {
      for (final item in _draft.items.where((i) => (i.customPrice ?? 0) > 0)) {
        final name = _lineFor(item)?.label ?? item.query;
        if (photo != null) {
          await state.api.submitProof(token: token, name: name, store: store, city: city.city, price: item.customPrice!, photo: photo);
        } else {
          await state.api.shareShelfPrice(token: token, name: name, store: store, city: city.city, price: item.customPrice!);
        }
        sent++;
      }
      messenger.showSnackBar(SnackBar(content: Text(photo != null
          ? 'Thanks! $sent sent with your proof for review.'
          : 'Thanks! $sent shared with shoppers in ${city.city}.')));
    } on ApiException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.message)));
    }
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
        onChanged: _search,
        decoration: InputDecoration(
          hintText: 'Search itlog, Piatos, or type a list',
          border: const OutlineInputBorder(),
          suffixIcon: IconButton(
            tooltip: 'Add',
            onPressed: _draft.items.length >= maxItems ? null : _add,
            icon: const Icon(Icons.add_circle),
          ),
        ),
      ),
      for (final item in _suggestions) SuggestionTile(item: item, onTap: () => _pickSuggestion(item)),
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
        current?.status == 'estimated' ||
        current?.status == 'needs_price' ||
        current?.status == 'no_match';
    final note = switch (current?.status) {
      'matched' => '${peso(current!.unitPrice)} per ${current.selected!.unit}',
      'reported' => 'Reported at ${current!.reportedStore}',
      'estimated' => '≈ ${peso(current!.unitPrice)}, an estimate. Enter the shelf price if you know it.',
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
