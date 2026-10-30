import 'package:flutter/material.dart';

import '../purchases.dart';
import '../state.dart';
import '../widgets.dart';

const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  final _store = PurchaseStore();
  List<Purchase> _purchases = const [];
  late ReportPeriod _period;
  String _selected = 'This month';

  @override
  void initState() {
    super.initState();
    _period = _presets.values.first;
    _load();
  }

  Map<String, ReportPeriod> get _presets {
    final now = DateTime.now();
    return {
      'This month': ReportPeriod.lastMonths(1, now),
      'Last month': ReportPeriod(DateTime(now.year, now.month - 1), 1),
      'Last 3 months': ReportPeriod.lastMonths(3, now),
      'Last 6 months': ReportPeriod.lastMonths(6, now),
      'This year': ReportPeriod.year(now.year),
      'Last year': ReportPeriod.year(now.year - 1),
    };
  }

  Future<void> _load() async {
    final purchases = await _store.read();
    if (mounted) setState(() => _purchases = purchases);
  }

  @override
  Widget build(BuildContext context) {
    final shown = _period.select(_purchases);
    final total = sumTotal(shown);
    final prior = sumTotal(_period.previous.select(_purchases));
    final change = total - prior;
    final months = totalsByMonth(_period, _purchases);
    final peak = months.values.fold<double>(1, (a, b) => a > b ? a : b);

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(padding: const EdgeInsets.all(16), children: [
        Text('Spending reports', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 4, children: [
          for (final entry in _presets.entries)
            ChoiceChip(
              label: Text(entry.key),
              selected: _selected == entry.key,
              onSelected: (_) => setState(() {
                _selected = entry.key;
                _period = entry.value;
              }),
            ),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: _Stat(label: 'This period', value: peso(total))),
          const SizedBox(width: 10),
          Expanded(child: _Stat(label: 'Previous period', value: peso(prior))),
        ]),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(
            child: _Stat(
              label: 'Change',
              value: prior == 0 ? 'No earlier data' : '${change >= 0 ? '▲' : '▼'} ${peso(change.abs())}',
            ),
          ),
          const SizedBox(width: 10),
          Expanded(child: _Stat(label: 'Purchases saved', value: '${shown.length}')),
        ]),
        if (_period.months > 1) ...[
          const SizedBox(height: 14),
          Card3d(
            child: SizedBox(
              height: 150,
              child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                for (final entry in months.entries)
                  Expanded(
                    child: Tooltip(
                      message: '${_months[entry.key.month - 1]} ${entry.key.year}: ${peso(entry.value)}',
                      child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                        Container(
                          height: 2 + 118 * entry.value / peak,
                          margin: const EdgeInsets.symmetric(horizontal: 3),
                          decoration: const BoxDecoration(
                            color: Color(0xFF1C7A43),
                            borderRadius: BorderRadius.vertical(top: Radius.circular(4)),
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(_months[entry.key.month - 1], style: const TextStyle(fontSize: 10)),
                      ]),
                    ),
                  ),
              ]),
            ),
          ),
        ],
        const SizedBox(height: 14),
        Text('Saved purchases', style: Theme.of(context).textTheme.titleMedium),
        if (shown.isEmpty)
          const Message(text: 'Nothing here yet. Finish a list, then tap Save this purchase.'),
        for (final purchase in shown)
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(purchase.name),
            subtitle: Text('${_months[purchase.date.month - 1]} ${purchase.date.day}, ${purchase.date.year} · ${purchase.lines.length} items'),
            trailing: Row(mainAxisSize: MainAxisSize.min, children: [
              Text(peso(purchase.total), style: const TextStyle(fontWeight: FontWeight.w700)),
              IconButton(
                tooltip: 'Delete',
                onPressed: () async {
                  await _store.delete(purchase.id);
                  _load();
                },
                icon: const Icon(Icons.delete_outline),
              ),
            ]),
          ),
      ]),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Card3d(
      padding: 12,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 2),
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Text(value, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w800)),
        ),
      ]),
    );
  }
}
