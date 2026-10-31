import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import 'api.dart';
import 'state.dart';

/// The cheapest store for the list, drawn on an in-app map from the shopper's position.
class BestStoreCard extends StatefulWidget {
  const BestStoreCard({super.key, required this.queries});

  final List<String> queries;

  @override
  State<BestStoreCard> createState() => _BestStoreCardState();
}

class _BestStoreCardState extends State<BestStoreCard> {
  StoreOffer? _best;
  RouteInfo? _route;
  String _loadedFor = '';

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _load();
  }

  @override
  void didUpdateWidget(BestStoreCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    _load();
  }

  Future<void> _load() async {
    final state = AppScope.of(context);
    final key = '${widget.queries.join('|')}|${state.city?.city}|${state.latitude}';
    if (key == _loadedFor || widget.queries.isEmpty) return;
    _loadedFor = key;
    try {
      final best = await state.api.bestStore(widget.queries, state.city?.city, state.latitude, state.longitude);
      RouteInfo? route;
      if (best != null && state.latitude != null) {
        route = await state.api.route(state.latitude!, state.longitude!, best.latitude, best.longitude);
      }
      if (mounted) {
        setState(() {
          _best = best;
          _route = route;
        });
      }
    } on ApiException {
      if (mounted) setState(() => _best = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.queries.isEmpty) return const SizedBox.shrink();
    final state = AppScope.of(context);
    final best = _best;
    final route = _route;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        gradient: const LinearGradient(colors: [Color(0xFF0F4023), Color(0xFF0B2616)]),
        borderRadius: BorderRadius.circular(18),
        boxShadow: const [
          BoxShadow(color: Color(0xFF081A10), offset: Offset(0, 5)),
          BoxShadow(color: Color(0x5514532D), offset: Offset(0, 14), blurRadius: 22),
        ],
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(best == null ? 'Your closest store' : 'Cheapest store for your list',
            style: const TextStyle(color: Color(0xFFFFC65C), fontWeight: FontWeight.w700)),
        const SizedBox(height: 4),
        if (best == null)
          _ClosestStore(city: state.city, me: state.latitude == null ? null : LatLng(state.latitude!, state.longitude!))
        else ...[
          Text(best.storeName, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
          Text(peso(best.total), style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w800)),
          Text(
            '${best.itemsFound} items at this store${route == null ? '' : ' · ${route.distanceKm.toStringAsFixed(1)} km${route.road ? ' by road' : ' straight-line'}'}${route?.durationMin == null ? '' : ' · about ${route!.durationMin} min'}',
            style: const TextStyle(color: Color(0xFFD3E8D9)),
          ),
          const SizedBox(height: 10),
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: SizedBox(
              height: 210,
              child: _RouteMap(
                key: ValueKey('${best.latitude}$route'),
                store: LatLng(best.latitude, best.longitude),
                me: state.latitude == null ? null : LatLng(state.latitude!, state.longitude!),
                path: route?.path.map((p) => LatLng(p[0], p[1])).toList() ?? const [],
              ),
            ),
          ),
          const SizedBox(height: 6),
          const Text('Based on prices shoppers reported in the last 30 days.',
              style: TextStyle(color: Color(0xFFB8CFBF), fontSize: 12)),
        ],
      ]),
    );
  }
}

class _ClosestStore extends StatelessWidget {
  const _ClosestStore({required this.city, required this.me});

  final CityInfo? city;
  final LatLng? me;

  @override
  Widget build(BuildContext context) {
    final store = city != null && city!.stores.isNotEmpty ? city!.stores.first : null;
    if (store == null) {
      return const Text('Turn on location to see the stores near you.', style: TextStyle(color: Color(0xFFD3E8D9)));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(store.name, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
      Text('${store.type} · ${store.distanceKm.toStringAsFixed(1)} km away', style: const TextStyle(color: Color(0xFFD3E8D9))),
      const SizedBox(height: 10),
      ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: SizedBox(
          height: 210,
          child: _RouteMap(store: LatLng(store.latitude, store.longitude), me: me, path: const []),
        ),
      ),
      const SizedBox(height: 6),
      const Text('The cheapest store will appear here once store prices near you are known.',
          style: TextStyle(color: Color(0xFFB8CFBF), fontSize: 12)),
    ]);
  }
}

class _RouteMap extends StatelessWidget {
  const _RouteMap({super.key, required this.store, required this.me, required this.path});

  final LatLng store;
  final LatLng? me;
  final List<LatLng> path;

  @override
  Widget build(BuildContext context) {
    final points = [store, if (me != null) me!, ...path];
    return FlutterMap(
      options: MapOptions(
        initialCenter: store,
        initialZoom: 15,
        initialCameraFit: points.length > 1
            ? CameraFit.coordinates(coordinates: points, padding: const EdgeInsets.all(34))
            : null,
      ),
      children: [
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.groceryprice.grocery_price_finder',
        ),
        if (path.length > 1)
          PolylineLayer(polylines: [Polyline(points: path, strokeWidth: 5, color: const Color(0xFF14532D))]),
        MarkerLayer(markers: [
          Marker(point: store, width: 40, height: 40, child: const Icon(Icons.storefront, color: Color(0xFFC9760F), size: 34)),
          if (me != null)
            Marker(point: me!, width: 40, height: 40, child: const Icon(Icons.my_location, color: Color(0xFF2A78D6), size: 30)),
        ]),
        const Align(
          alignment: Alignment.bottomRight,
          child: ColoredBox(
            color: Color(0xCCFFFFFF),
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: 4),
              child: Text('© OpenStreetMap contributors', style: TextStyle(fontSize: 10)),
            ),
          ),
        ),
      ],
    );
  }
}


/// Shows a store on a map inside the app.
void showStoreMap(BuildContext context, String name, double latitude, double longitude) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (sheet) => SizedBox(
      height: MediaQuery.sizeOf(sheet).height * 0.7,
      child: Column(children: [
        Padding(padding: const EdgeInsets.all(14), child: Text(name, style: Theme.of(sheet).textTheme.titleMedium)),
        Expanded(child: _RouteMap(store: LatLng(latitude, longitude), me: null, path: const [])),
      ]),
    ),
  );
}
