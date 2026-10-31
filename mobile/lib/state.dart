import 'dart:async';

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'drafts.dart';

const _budgetKey = 'budget_v1';

/// Shared app data. Device coordinates are used once and never kept.
class AppState extends ChangeNotifier {
  AppState({Api? api, DraftStore? drafts})
      : api = api ?? Api(),
        drafts = drafts ?? DraftStore();

  final Api api;
  final DraftStore drafts;

  CityInfo? city;
  double? latitude; // Held in memory only.
  double? longitude;
  bool locating = false;
  String? locationError;

  int liveVersion = 0;
  Timer? _liveTimer;

  /// Prices change on the server, so open screens check and reload by themselves.
  void startLiveUpdates() {
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
