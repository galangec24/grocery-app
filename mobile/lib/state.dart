import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'drafts.dart';

const _budgetKey = 'budget_v1';
const _refreshKey = 'refresh_token';
const _nameKey = 'shopper_name';

/// Shared app data. Device coordinates are used once and never kept.
class AppState extends ChangeNotifier {
  AppState({Api? api, DraftStore? drafts, this.liveUpdates = true})
      : api = api ?? Api(),
        drafts = drafts ?? DraftStore();

  final Api api;
  final DraftStore drafts;
  final bool liveUpdates;

  CityInfo? city;
  double? latitude; // Held in memory only.
  double? longitude;
  bool locating = false;
  String? locationError;

  static const _secure = FlutterSecureStorage();
  Session? session;

  Future<void> signIn(String email, String password, {String? name}) async {
    session = await api.signIn(email, password, name: name);
    await _secure.write(key: _refreshKey, value: session!.refreshToken);
    await _secure.write(key: _nameKey, value: session!.name);
    notifyListeners();
  }

  /// A fresh access token, or null when the shopper needs to sign in.
  Future<String?> accessToken() async {
    final refresh = session?.refreshToken ?? await _secure.read(key: _refreshKey);
    if (refresh == null) return null;
    try {
      final token = await api.refresh(refresh);
      session ??= Session(name: await _secure.read(key: _nameKey) ?? '', accessToken: token, refreshToken: refresh);
      session!.accessToken = token;
      return token;
    } on ApiException {
      await _secure.delete(key: _refreshKey);
      session = null;
      return null;
    }
  }

  int liveVersion = 0;
  Timer? _liveTimer;

  /// Prices change on the server, so open screens check and reload by themselves.
  void startLiveUpdates() {
    if (!liveUpdates) return;
    _liveTimer?.cancel();
    _liveTimer = Timer.periodic(const Duration(seconds: 30), (_) => checkForNewPrices());
  }

  Future<void> checkForNewPrices() async {
    try {
      final version = await api.liveVersion();
      if (version != liveVersion) {
        liveVersion = version;
        notifyListeners();
      }
    } on ApiException {
      return; // The next check will try again.
    }
  }

  @override
  void dispose() {
    _liveTimer?.cancel();
    super.dispose();
  }

  double? budget;
  bool budgetLoaded = false;
  double spent = 0;

  Future<void> loadBudget() async {
    final prefs = await SharedPreferences.getInstance();
    budget = prefs.getDouble(_budgetKey);
    budgetLoaded = true;
    notifyListeners();
  }

  Future<void> setBudget(double? value) async {
    budget = value != null && value > 0 ? value : null;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    if (budget == null) {
      await prefs.remove(_budgetKey);
    } else {
      await prefs.setDouble(_budgetKey, budget!);
    }
  }

  void setSpent(double value) {
    if (spent == value) return;
    spent = value;
    notifyListeners();
  }

  Future<void> useDeviceLocation() async {
    _start();
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        throw ApiException('Location is off. Type your city instead.');
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        throw ApiException(
            'Location permission is off. Type your city instead; everything still works.');
      }
      final position = await Geolocator.getCurrentPosition();
      latitude = position.latitude;
      longitude = position.longitude;
      city = await api.resolveLocation(position.latitude, position.longitude);
    } on ApiException catch (error) {
      locationError = error.message;
    } catch (_) {
      locationError = "Couldn't get your location. Type your city instead.";
    }
    _finish();
  }

  Future<void> chooseCity(String name) async {
    _start();
    try {
      city = await api.resolveCity(name);
    } on ApiException catch (error) {
      locationError = error.message;
    }
    _finish();
  }

  void clearCity() {
    city = null;
    latitude = null;
    longitude = null;
    locationError = null;
    notifyListeners();
  }

  void _start() {
    locating = true;
    locationError = null;
    notifyListeners();
  }

  void _finish() {
    locating = false;
    notifyListeners();
  }
}

class AppScope extends InheritedNotifier<AppState> {
  const AppScope({super.key, required AppState state, required super.child})
      : super(notifier: state);

  static AppState of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<AppScope>()!.notifier!;
}

String peso(double value) {
  final fixed = value.toStringAsFixed(2);
  final parts = fixed.split('.');
  final whole = parts[0].replaceAllMapped(
      RegExp(r'(\d)(?=(\d{3})+$)'), (m) => '${m[1]},');
  return '₱$whole.${parts[1]}';
}
