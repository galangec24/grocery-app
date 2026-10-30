import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

import 'api.dart';
import 'drafts.dart';

/// Shared app data. Device coordinates are used once and never kept.
class AppState extends ChangeNotifier {
  AppState({Api? api, DraftStore? drafts})
      : api = api ?? Api(),
        drafts = drafts ?? DraftStore();

  final Api api;
  final DraftStore drafts;

  CityInfo? city;
  bool locating = false;
  String? locationError;

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
