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

class BasketLine {
  BasketLine.fromJson(Map<String, dynamic> json)
      : query = json['query'] as String,
        quantity = json['quantity'] as int,
        matched = json['status'] == 'matched',
        lineTotal = (json['line_total'] as num).toDouble(),
        selected = json['selected'] == null
            ? null
            : PriceRow.fromJson(json['selected'] as Map<String, dynamic>),
        candidates = ((json['candidates'] as List?) ?? const [])
            .map((c) => Candidate.fromJson(c as Map<String, dynamic>))
            .toList();

  final String query;
  final int quantity;
  final bool matched;
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

class Api {
  Api({http.Client? client}) : _client = client ?? http.Client();
  final http.Client _client;

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

  Future<Basket> basket(List<Map<String, dynamic>> items, {String? island}) async {
    final data = await _send(() => _client.post(
          _uri('/market/basket'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'items': items, 'island': island}),
        ));
    return Basket.fromJson(data as Map<String, dynamic>);
  }
}
