import 'dart:convert';
import 'dart:math';

import 'package:shared_preferences/shared_preferences.dart';

const maxItems = 30;
const _storageKey = 'drafts_v2';

String newId() =>
    '${DateTime.now().microsecondsSinceEpoch}-${Random().nextInt(1 << 32)}';

class DraftItem {
  DraftItem({String? id, required this.query, this.quantity = 1, this.priceId, this.label, this.customPrice, this.checked = false})
      : id = id ?? newId();

  DraftItem.fromJson(Map<String, dynamic> json)
      : id = json['id'] as String,
        query = json['query'] as String,
        quantity = json['quantity'] as int,
        priceId = json['priceId'] as String?,
        label = json['label'] as String?,
        customPrice = (json['customPrice'] as num?)?.toDouble(),
        checked = (json['checked'] as bool?) ?? false;

  final String id;
  final String query;
  int quantity;
  String? priceId;
  String? label;
  double? customPrice;
  bool checked;

  Map<String, dynamic> toJson() => {
        'id': id,
        'query': query,
        'quantity': quantity,
        'priceId': priceId,
        'label': label,
        'customPrice': customPrice,
        'checked': checked,
      };
}

class Draft {
  Draft({String? id, this.name = '', List<DraftItem>? items, DateTime? updatedAt})
      : id = id ?? newId(),
        items = items ?? [],
        updatedAt = updatedAt ?? DateTime.now();

  Draft.fromJson(Map<String, dynamic> json)
      : id = json['id'] as String,
        name = json['name'] as String,
        updatedAt = DateTime.parse(json['updatedAt'] as String),
        lastTotal = (json['lastTotal'] as num?)?.toDouble(),
        items = (json['items'] as List)
            .map((i) => DraftItem.fromJson(i as Map<String, dynamic>))
            .toList();

  final String id;
  String name;
  List<DraftItem> items;
  DateTime updatedAt;
  double? lastTotal;

  /// Starts a new list from this one, with nothing ticked off.
  Draft duplicate() => Draft(
        name: '${name.isEmpty ? 'Untitled draft' : name} copy',
        items: [
          for (final i in items)
            DraftItem(query: i.query, quantity: i.quantity, priceId: i.priceId, label: i.label, customPrice: i.customPrice),
        ],
      )..lastTotal = lastTotal;

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'updatedAt': updatedAt.toIso8601String(),
        'lastTotal': lastTotal,
        'items': items.map((i) => i.toJson()).toList(),
      };

  /// Adds an item, raising the quantity instead of duplicating it.
  void add(DraftItem item) {
    for (final existing in items) {
      if (existing.query.toLowerCase() == item.query.toLowerCase()) {
        existing.quantity = min(existing.quantity + item.quantity, 999);
        return;
      }
    }
    if (items.length < maxItems) items.add(item);
  }
}

final _leadingX = RegExp(r'^(\d{1,3})\s*x\s+(.+)$', caseSensitive: false);
final _leadingNumber = RegExp(r'^(\d{1,3})\s+([a-z].*)$', caseSensitive: false);
final _trailing = RegExp(r'^(.+?)\s*x\s*(\d{1,3})$', caseSensitive: false);
final _sizeWord = RegExp(r'^(kg|g|l|ml|pcs?|pieces?)\b', caseSensitive: false);

/// Splits pasted text on new lines or commas. "2 x milk", "milk x2" and
/// "3 eggs" set a quantity; "5 kg rice" stays one item.
List<DraftItem> parseItems(String text) {
  final merged = <String, DraftItem>{};
  for (final raw in text.split(RegExp(r'[\n,]+'))) {
    var line = raw.trim();
    if (line.isEmpty) continue;
    var quantity = 1;
    final leading = _leadingX.firstMatch(line) ?? _leadingNumber.firstMatch(line);
    final trailing = _trailing.firstMatch(line);
    if (leading != null && !_sizeWord.hasMatch(leading.group(2)!)) {
      quantity = int.parse(leading.group(1)!);
      line = leading.group(2)!;
    } else if (trailing != null) {
      quantity = int.parse(trailing.group(2)!);
      line = trailing.group(1)!;
    }
    quantity = max(quantity, 1);
    final key = line.toLowerCase();
    final existing = merged[key];
    if (existing != null) {
      existing.quantity += quantity;
    } else {
      merged[key] = DraftItem(query: line, quantity: quantity);
    }
  }
  return merged.values.toList();
}

class DraftStore {
  Future<List<Draft>> read() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_storageKey);
    if (raw == null) return [];
    try {
      final drafts = (jsonDecode(raw) as List)
          .map((d) => Draft.fromJson(d as Map<String, dynamic>))
          .toList();
      drafts.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
      return drafts;
    } on FormatException {
      return [];
    }
  }

  Future<void> save(Draft draft) async {
    draft.updatedAt = DateTime.now();
    final drafts = (await read()).where((d) => d.id != draft.id).toList()
      ..insert(0, draft);
    await _write(drafts);
  }

  Future<void> delete(String id) async {
    await _write((await read()).where((d) => d.id != id).toList());
  }

  Future<void> _write(List<Draft> drafts) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
        _storageKey, jsonEncode(drafts.map((d) => d.toJson()).toList()));
  }
}
