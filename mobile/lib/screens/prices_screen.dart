import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api.dart';
import '../drafts.dart';
import '../state.dart';
import '../widgets.dart';

class PricesScreen extends StatefulWidget {
  const PricesScreen({super.key});

  @override
  State<PricesScreen> createState() => _PricesScreenState();
}

class _PricesScreenState extends State<PricesScreen> {
  final _search = TextEditingController();
  final _cityField = TextEditingController();
  List<PriceRow>? _rows;
  List<CatalogItem> _catalog = const [];
  String? _error;
  String? _loadedIsland;
  bool _loaded = false;
  String _source = 'all';

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final island = AppScope.of(context).city?.island;
    if (!_loaded || island != _loadedIsland) {
      _loaded = true;
      _loadedIsland = island;
      _load();
    }
  }

  @override
  void dispose() {
    _search.dispose();
    _cityField.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final state = AppScope.of(context);
    setState(() => _error = null);
    try {
      final rows = await state.api.prices(island: state.city?.island);
      if (mounted) setState(() => _rows = rows);
      final catalog = await state.api.catalog();
      if (mounted) setState(() => _catalog = catalog);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  List<PriceRow> get _shown {
    final words = _search.text.toLowerCase().split(RegExp(r'\s+')).where((w) => w.isNotEmpty);
    return (_rows ?? const <PriceRow>[]).where((row) {
      if (_source == 'srp' && !row.isSrp) return false;
      if (_source == 'market' && row.isSrp) return false;
      final text = '${row.commodity} ${row.specification} ${row.category}'.toLowerCase();
      return words.every((w) =>
          text.contains(w) || (w.endsWith('s') && text.contains(w.substring(0, w.length - 1))));
    }).toList();
  }

  List<CatalogItem> get _brands {
    final words = _search.text.toLowerCase().split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();
    if (words.isEmpty) return const [];
    return _catalog.where((item) {
      return words.every((w) =>
          item.keywords.contains(w) || (w.endsWith('s') && item.keywords.contains(w.substring(0, w.length - 1))));
    }).take(24).toList();
  }

  Future<void> _addBrand(CatalogItem item) async {
    final state = AppScope.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final all = await state.drafts.read();
    final draft = all.isNotEmpty ? all.first : Draft(name: 'My list');
    draft.add(DraftItem(query: '${item.name} ${item.size}'));
    await state.drafts.save(draft);
    messenger.showSnackBar(SnackBar(content: Text('Added to ${draft.name}. Enter the shelf price there.')));
  }

  Future<void> _addToDraft(PriceRow row) async {
    final state = AppScope.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final all = await state.drafts.read();
    final draft = all.isNotEmpty ? all.first : Draft(name: 'My list');
    draft.add(DraftItem(query: row.label, priceId: row.id, label: row.label));
    await state.drafts.save(draft);
    messenger.showSnackBar(SnackBar(content: Text('Added to ${draft.name}')));
  }

  @override
  Widget build(BuildContext context) {
    final shown = _shown;
    final brands = _brands;
    final columns = (MediaQuery.sizeOf(context).width / 420).floor().clamp(1, 3);
    return RefreshIndicator(
      onRefresh: _load,
      child: CustomScrollView(slivers: [
        SliverToBoxAdapter(child: HeroHeader(rows: _rows)),
        SliverToBoxAdapter(child: _CityCard(field: _cityField)),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
            child: TextField(
              controller: _search,
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(
                hintText: 'Search rice, Mega Sardines, Piatos…',
                prefixIcon: Icon(Icons.search),
                border: OutlineInputBorder(),
              ),
            ),
          ),
        ),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            child: SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'all', label: Text('All')),
                ButtonSegment(value: 'srp', label: Text('Standard')),
                ButtonSegment(value: 'market', label: Text('Market')),
              ],
              selected: {_source},
              onSelectionChanged: (value) => setState(() => _source = value.first),
            ),
          ),
        ),
        if (brands.isNotEmpty)
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Found in stores', style: Theme.of(context).textTheme.titleMedium),
                const Text('No official price yet. Add one to your draft and enter the shelf price.'),
                const SizedBox(height: 6),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  for (final item in brands)
                    ActionChip(
                      avatar: const Icon(Icons.add, size: 18),
                      label: Text('${item.name} ${item.size}'),
                      onPressed: () => _addBrand(item),
                    ),
                ]),
              ]),
            ),
          ),
        if (_error != null)
          SliverToBoxAdapter(child: Message(text: _error!, action: 'Try again', onAction: _load))
        else if (_rows == null)
          const SliverToBoxAdapter(
              child: Padding(padding: EdgeInsets.all(32), child: Center(child: CircularProgressIndicator())))
        else if (_rows!.isEmpty)
          const SliverToBoxAdapter(child: Message(text: 'Official prices are being collected. Check back in a few minutes.'))
        else if (shown.isEmpty && brands.isEmpty)
          const SliverToBoxAdapter(child: Message(text: 'Nothing matches. Try one word, like “rice”.'))
        else
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            sliver: SliverGrid.builder(
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: columns,
                mainAxisExtent: 124,
                crossAxisSpacing: 10,
                mainAxisSpacing: 10,
              ),
              itemCount: shown.length,
              itemBuilder: (_, i) => PriceCard(row: shown[i], onAdd: () => _addToDraft(shown[i])),
            ),
          ),
      ]),
    );
  }
}

class _CityCard extends StatelessWidget {
  const _CityCard({required this.field});

  final TextEditingController field;

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final city = state.city;
    return Card3d(
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(city == null ? 'Find your city' : '${city.city}, ${city.region}',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 4),
        Text(city == null
            ? 'See official prices for your area and every mall and supermarket in your city.'
            : city.storesAvailable
                ? '${city.storeCount} supermarkets and malls found. Official SRPs apply to all of them.'
                : "The store map is busy, so stores can't be listed right now. Official SRPs still apply across your city."),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          FilledButton.icon(
            onPressed: state.locating ? null : state.useDeviceLocation,
            icon: const Icon(Icons.my_location),
            label: Text(state.locating ? 'Finding your city…' : city == null ? 'Use my location' : 'Refresh location'),
          ),
          if (city != null) OutlinedButton(onPressed: state.clearCity, child: const Text('Clear')),
        ]),
        if (city == null) ...[
          const SizedBox(height: 8),
          TextField(
            controller: field,
            textInputAction: TextInputAction.search,
            onSubmitted: (value) {
              if (value.trim().isNotEmpty) state.chooseCity(value.trim());
            },
            decoration: const InputDecoration(
              hintText: 'Or type a city, like Davao City',
              isDense: true,
              border: OutlineInputBorder(),
            ),
          ),
        ],
        if (state.locationError != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(state.locationError!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        if (city != null && !city.metroManila)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
                'Daily market prices are measured in Metro Manila, so treat them as a reference here. SRPs shown are set for ${city.island}.',
                style: Theme.of(context).textTheme.bodySmall),
          ),
        if (city != null && city.stores.isNotEmpty) ...[
          const SizedBox(height: 8),
          SizedBox(
            height: 62,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: city.stores.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (_, i) {
                final store = city.stores[i];
                return ActionChip(
                  avatar: Icon(store.type == 'Mall' ? Icons.storefront : Icons.shopping_cart, size: 18),
                  label: Text('${store.name}\n${store.distanceKm.toStringAsFixed(1)} km'),
                  onPressed: () => launchUrl(
                    Uri.parse('https://www.google.com/maps/search/?api=1&query=${store.latitude},${store.longitude}'),
                    mode: LaunchMode.externalApplication,
                  ),
                );
              },
            ),
          ),
          Text(city.attribution, style: Theme.of(context).textTheme.bodySmall),
        ],
      ]),
    );
  }
}
