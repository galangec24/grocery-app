import 'dart:convert';

import 'package:http/http.dart' as http;

const apiBase = String.fromEnvironment(
  'API_URL',
  defaultValue: 'https://grocery-price-finder-api.onrender.com',
);

class ApiException implements Exception {
  ApiException(this.message);
  final String message;
  @override
  String toString() => message;
}

class PriceRow {
  PriceRow.fromJson(Map<String, dynamic> json)
      : id = json['id'] as String,
        kind = json['kind'] as String,
        sourceLabel = json['source_label'] as String,
        category = json['category'] as String,
        commodity = json['commodity'] as String,
        specification = (json['specification'] as String?) ?? '',
        unit = json['unit'] as String,
        region = json['region'] as String,
        price = (json['price'] as num).toDouble(),
        change = (json['change'] as num?)?.toDouble(),
        changePct = (json['change_pct'] as num?)?.toDouble(),
        reportDate = json['report_date'] as String,
        trend = ((json['trend'] as List?) ?? const [])
            .map((v) => (v as num).toDouble())
            .toList();

  final String id;
  final String kind;
  final String sourceLabel;
  final String category;
  final String commodity;
  final String specification;
  final String unit;
  final String region;
  final double price;
  final double? change;
  final double? changePct;
  final String reportDate;
  final List<double> trend;

  bool get isSrp => kind == 'srp';
  String get label =>
      specification.isEmpty ? commodity : '$commodity, $specification';
}

class CityStore {
  CityStore.fromJson(Map<String, dynamic> json)
      : name = json['name'] as String,
        type = json['type'] as String,
        latitude = (json['latitude'] as num).toDouble(),
        longitude = (json['longitude'] as num).toDouble(),
        distanceKm = (json['distance_km'] as num).toDouble();

  final String name;
  final String type;
  final double latitude;
  final double longitude;
  final double distanceKm;
}

class CityInfo {
  CityInfo.fromJson(Map<String, dynamic> json)
      : city = json['city'] as String,
        region = json['region'] as String,
        island = json['island'] as String,
        metroManila = json['metro_manila'] as bool,
        storeCount = json['store_count'] as int,
        storesAvailable = json['stores_available'] as bool,
        attribution = json['attribution'] as String,
        stores = (json['stores'] as List)
            .map((s) => CityStore.fromJson(s as Map<String, dynamic>))
            .toList();

  final String city;
  final String region;
  final String island;
  final bool metroManila;
  final int storeCount;
  final bool storesAvailable;
  final String attribution;
  final List<CityStore> stores;
}

class MallPrice {
  MallPrice.fromJson(Map<String, dynamic> json)
      : itemName = json['item_name'] as String,
        storeName = json['store_name'] as String,
        origin = json['origin'] as String,
        price = (json['price'] as num).toDouble();

  final String itemName;
  final String storeName;
  final String origin;
  final double price;
}

class CatalogItem {
  CatalogItem.fromJson(Map<String, dynamic> json)
      : id = json['id'] as String,
        name = json['name'] as String,
        category = json['category'] as String,
        size = json['size'] as String,
        variant = (json['variant'] as String?) ?? '',
        keywords = json['keywords'] as String,
        price = ((json['auto_price'] as Map<String, dynamic>?)?['price'] as num?)?.toDouble(),
        isStorePrice = (json['auto_price'] as Map<String, dynamic>?)?['kind'] == 'store';

  final String id;
  final String name;
  final String category;
  final String size;
  final String variant;
  final String keywords;
  final double? price;
  final bool isStorePrice;
}

class Suggestion {
  Suggestion.fromJson(Map<String, dynamic> json)
      : id = json['id'] as String,
        name = json['name'] as String,
        size = (json['size'] as String?) ?? '',
        category = json['category'] as String,
        imageUrl = json['image_url'] as String?,
        price = (json['price'] as num?)?.toDouble(),
        priceLabel = json['price_label'] as String?,
        priceId = json['price_id'] as String?;

  final String id;
  final String name;
  final String size;
  final String category;
  final String? imageUrl;
  final double? price;
  final String? priceLabel;
  final String? priceId;

  String get label => size.isEmpty ? name : '$name $size';
}

class StoreOffer {
  StoreOffer.fromJson(Map<String, dynamic> json)
      : storeName = json['store_name'] as String,
        latitude = (json['latitude'] as num).toDouble(),
        longitude = (json['longitude'] as num).toDouble(),
        total = (json['total'] as num).toDouble(),
        itemsFound = json['items_found'] as int;

  final String storeName;
  final double latitude;
  final double longitude;
  final double total;
  final int itemsFound;
}

class RouteInfo {
  RouteInfo.fromJson(Map<String, dynamic> json)
      : path = (json['path'] as List).map((p) => (p as List).map((v) => (v as num).toDouble()).toList()).toList(),
        distanceKm = (json['distance_km'] as num).toDouble(),
        durationMin = json['duration_min'] as int?,
        road = json['road'] as bool;

  final List<List<double>> path;
  final double distanceKm;
  final int? durationMin;
  final bool road;
}

class BasketLine {
  BasketLine.fromJson(Map<String, dynamic> json)
      : query = json['query'] as String,
        quantity = json['quantity'] as int,
        status = json['status'] as String,
        label = json['label'] as String,
        reportedStore = (json['report'] as Map<String, dynamic>?)?['store_name'] as String?,
        unitPrice = (json['unit_price'] as num).toDouble(),
        lineTotal = (json['line_total'] as num).toDouble(),
        selected = json['selected'] == null
            ? null
            : PriceRow.fromJson(json['selected'] as Map<String, dynamic>),
        candidates = ((json['candidates'] as List?) ?? const [])
            .map((c) => Candidate.fromJson(c as Map<String, dynamic>))
            .toList();

  final String query;
  final int quantity;
  final String status;
  final String label;
  final String? reportedStore;
  final double unitPrice;
  final double lineTotal;
  final PriceRow? selected;
  final List<Candidate> candidates;
}

class Candidate {
  Candidate.fromJson(Map<String, dynamic> json)
      : id = json['id'] as String,
        commodity = json['commodity'] as String,
        specification = (json['specification'] as String?) ?? '',
        price = (json['price'] as num).toDouble();

  final String id;
  final String commodity;
  final String specification;
  final double price;

  String get label =>
      specification.isEmpty ? commodity : '$commodity, $specification';
}

class Basket {
  Basket.fromJson(Map<String, dynamic> json)
      : total = (json['total'] as num).toDouble(),
        itemsMatched = json['items_matched'] as int,
        lines = (json['lines'] as List)
            .map((l) => BasketLine.fromJson(l as Map<String, dynamic>))
            .toList();

  final double total;
  final int itemsMatched;
  final List<BasketLine> lines;
}

class Session {
  Session({required this.name, required this.accessToken, required this.refreshToken});

  final String name;
  String accessToken;
  final String refreshToken;
}

class Api {
  Api({http.Client? client}) : _client = client ?? http.Client();
  final http.Client _client;

  Map<String, String> _bearer(String token) => {'Authorization': 'Bearer $token'};

  Future<Session> signIn(String email, String password, {String? name}) async {
    final data = await _send(() => _client.post(
          _uri(name == null ? '/auth/login' : '/auth/register'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'email': email,
            'password': password,
            if (name != null) 'full_name': name,
          }),
        ));
    return Session(
      name: data['user']['full_name'] as String,
      accessToken: data['access_token'] as String,
      refreshToken: data['refresh_token'] as String,
    );
  }

  Future<String> refresh(String refreshToken) async {
    final data = await _send(() => _client.post(
          _uri('/auth/refresh'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'refresh_token': refreshToken}),
        ));
    return data['access_token'] as String;
  }

  Future<void> submitProof({
    required String token,
    required String name,
    required CityStore store,
    required String city,
    required double price,
    required List<int> photo,
  }) async {
    final request = http.MultipartRequest('POST', _uri('/market/proofs'))
      ..headers.addAll(_bearer(token))
      ..fields.addAll({
        'name': name,
        'store_name': store.name,
        'latitude': '${store.latitude}',
        'longitude': '${store.longitude}',
        'city': city,
        'price': '$price',
      })
      ..files.add(http.MultipartFile.fromBytes('photo', photo, filename: 'proof.jpg'));
    await _send(() async => http.Response.fromStream(await _client.send(request)));
  }

  Future<dynamic> _send(Future<http.Response> Function() request) async {
    final http.Response response;
    try {
      response = await request().timeout(const Duration(seconds: 75));
    } catch (_) {
      throw ApiException(
          "Can't reach the price server. It may be waking up, so please try again in a minute.");
    }
    final body = jsonDecode(utf8.decode(response.bodyBytes));
    if (response.statusCode >= 400) {
      final detail = body is Map ? body['detail'] : null;
      throw ApiException(
          detail is String ? detail : 'Request failed (${response.statusCode})');
    }
    return body;
  }

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$apiBase/api/v1$path').replace(queryParameters: query);

  Future<List<PriceRow>> prices({String? island}) async {
    final data = await _send(() => _client.get(
        _uri('/market/prices', island == null ? null : {'island': island})));
    return (data['results'] as List)
        .map((r) => PriceRow.fromJson(r as Map<String, dynamic>))
        .toList();
  }

  Future<List<CatalogItem>> catalog(String query) async {
    final data = await _send(() => _client.get(_uri('/market/catalog', {'q': query, 'limit': '24'})));
    return (data as List).map((c) => CatalogItem.fromJson(c as Map<String, dynamic>)).toList();
  }

  Future<List<String>> malls(String? city) async {
    final data = await _send(() => _client.get(_uri('/market/malls', {if (city != null) 'city': city})));
    return (data as List).map((m) => m['name'] as String).toList();
  }

  Future<List<MallPrice>> mallPrices(String mall, String query, String? city) async {
    final data = await _send(() => _client.get(_uri('/market/mall-prices', {
          'mall': mall,
          if (query.isNotEmpty) 'q': query,
          if (city != null) 'city': city,
        })));
    return (data['results'] as List).map((p) => MallPrice.fromJson(p as Map<String, dynamic>)).toList();
  }

  Future<CityInfo> resolveLocation(double latitude, double longitude) async {
    final data = await _send(() => _client.get(_uri('/location/resolve',
        {'latitude': '$latitude', 'longitude': '$longitude'})));
    return CityInfo.fromJson(data as Map<String, dynamic>);
  }

  Future<CityInfo> resolveCity(String city) async {
    final data = await _send(
        () => _client.get(_uri('/location/resolve', {'city': city})));
    return CityInfo.fromJson(data as Map<String, dynamic>);
  }

  Future<int> liveVersion() async {
    final data = await _send(() => _client.get(_uri('/market/live')));
    return data['version'] as int;
  }

  Future<List<Suggestion>> suggest(String query, {String? island, String? city}) async {
    final data = await _send(() => _client.get(_uri('/market/suggest', {
          'q': query,
          'limit': '6',
          if (island != null) 'island': island,
          if (city != null) 'city': city,
        })));
    return (data as List).map((s) => Suggestion.fromJson(s as Map<String, dynamic>)).toList();
  }

  Future<StoreOffer?> bestStore(List<String> items, String? city, double? latitude, double? longitude) async {
    final data = await _send(() => _client.post(
          _uri('/market/best-stores'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'items': items, 'city': city, 'latitude': latitude, 'longitude': longitude}),
        ));
    final best = data['best'];
    return best == null ? null : StoreOffer.fromJson(best as Map<String, dynamic>);
  }

  Future<RouteInfo> route(double fromLat, double fromLon, double toLat, double toLon) async {
    final data = await _send(() => _client.get(_uri('/location/route', {
          'from_lat': '$fromLat',
          'from_lon': '$fromLon',
          'to_lat': '$toLat',
          'to_lon': '$toLon',
        })));
    return RouteInfo.fromJson(data as Map<String, dynamic>);
  }

  Future<bool> shareShelfPrice({
    required String token,
    required String name,
    required CityStore store,
    required String city,
    required double price,
  }) async {
    final data = await _send(() => _client.post(
          _uri('/market/shelf-prices'),
          headers: {'Content-Type': 'application/json', ..._bearer(token)},
          body: jsonEncode({
            'name': name,
            'store_name': store.name,
            'latitude': store.latitude,
            'longitude': store.longitude,
            'city': city,
            'price': price,
          }),
        ));
    return data['held_for_review'] as bool;
  }

  Future<Basket> basket(List<Map<String, dynamic>> items, {String? island, String? city}) async {
    final data = await _send(() => _client.post(
          _uri('/market/basket'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'items': items, 'island': island, 'city': city}),
        ));
    return Basket.fromJson(data as Map<String, dynamic>);
  }
}
