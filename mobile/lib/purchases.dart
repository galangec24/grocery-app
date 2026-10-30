import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'drafts.dart';

const _key = 'purchases_v1';

class PurchaseLine {
  PurchaseLine({required this.name, required this.quantity, required this.unitPrice, required this.lineTotal});

  PurchaseLine.fromJson(Map<String, dynamic> json)
      : name = json['name'] as String,
        quantity = json['quantity'] as int,
        unitPrice = (json['unitPrice'] as num).toDouble(),
        lineTotal = (json['lineTotal'] as num).toDouble();

  final String name;
  final int quantity;
  final double unitPrice;
  final double lineTotal;

  Map<String, dynamic> toJson() =>
      {'name': name, 'quantity': quantity, 'unitPrice': unitPrice, 'lineTotal': lineTotal};
}

/// A saved shopping trip, kept on the device so no account is needed.
class Purchase {
  Purchase({String? id, required this.name, required this.date, required this.total, required this.lines})
      : id = id ?? newId();

  Purchase.fromJson(Map<String, dynamic> json)
      : id = json['id'] as String,
        name = json['name'] as String,
        date = DateTime.parse(json['date'] as String),
        total = (json['total'] as num).toDouble(),
        lines = (json['lines'] as List).map((l) => PurchaseLine.fromJson(l as Map<String, dynamic>)).toList();

  final String id;
  final String name;
  final DateTime date;
  final double total;
  final List<PurchaseLine> lines;

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'date': date.toIso8601String(),
        'total': total,
        'lines': lines.map((l) => l.toJson()).toList(),
      };
}

class PurchaseStore {
  Future<List<Purchase>> read() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null) return [];
    final purchases = (jsonDecode(raw) as List).map((p) => Purchase.fromJson(p as Map<String, dynamic>)).toList();
    purchases.sort((a, b) => b.date.compareTo(a.date));
    return purchases;
  }

  Future<void> save(Purchase purchase) async => _write([purchase, ...await read()]);

  Future<void> delete(String id) async => _write((await read()).where((p) => p.id != id).toList());

  Future<void> _write(List<Purchase> purchases) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, jsonEncode(purchases.map((p) => p.toJson()).toList()));
  }
}

/// An inclusive span of whole months.
class ReportPeriod {
  ReportPeriod(this.start, this.months);

  factory ReportPeriod.lastMonths(int count, DateTime now) =>
      ReportPeriod(DateTime(now.year, now.month - count + 1), count);

  factory ReportPeriod.year(int year) => ReportPeriod(DateTime(year), 12);

  final DateTime start;
  final int months;

  DateTime get end => DateTime(start.year, start.month + months);

  ReportPeriod get previous => ReportPeriod(DateTime(start.year, start.month - months), months);

  bool contains(DateTime date) => !date.isBefore(start) && date.isBefore(end);

  List<Purchase> select(List<Purchase> purchases) => purchases.where((p) => contains(p.date)).toList();
}

double sumTotal(List<Purchase> purchases) => purchases.fold(0, (sum, p) => sum + p.total);

Map<DateTime, double> totalsByMonth(ReportPeriod period, List<Purchase> purchases) {
  final totals = {
    for (var i = 0; i < period.months; i++) DateTime(period.start.year, period.start.month + i): 0.0,
  };
  for (final purchase in period.select(purchases)) {
    final month = DateTime(purchase.date.year, purchase.date.month);
    totals[month] = (totals[month] ?? 0) + purchase.total;
  }
  return totals;
}
