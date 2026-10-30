import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:grocery_price_finder/api.dart';
import 'package:grocery_price_finder/calculator.dart';
import 'package:grocery_price_finder/drafts.dart';
import 'package:grocery_price_finder/main.dart';
import 'package:grocery_price_finder/state.dart';
import 'package:grocery_price_finder/updates.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> row(String id, String commodity, double price, String kind) => {
      'id': id,
      'source_label': 'Official source',
      'kind': kind,
      'category': 'Rice',
      'commodity': commodity,
      'specification': '',
      'unit': 'kg',
      'region': 'Nationwide',
      'price': price,
      'change': null,
      'change_pct': null,
      'report_date': '2026-10-30',
      'trend': [price],
    };

AppState fakeState() => AppState(
      api: Api(
        client: MockClient((request) async {
          if (request.url.path.endsWith('/market/catalog')) {
            return http.Response(
              jsonEncode([
                {'id': 'c1', 'name': 'Jack n Jill Piatos Cheese', 'category': 'Junk Food', 'size': '85g', 'keywords': 'jack n jill piatos cheese 85g junk food chips'},
              ]),
              200,
            );
          }
          return http.Response(
            jsonEncode({
              'results': [
                row('a', 'Premium Rice, Local', 53.87, 'prevailing'),
                row('b', 'Bear Brand', 50, 'srp'),
              ],
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }),
      ),
    );

void main() {
  group('parseItems', () {
    test('reads lines and commas', () {
      final items = parseItems('rice\neggs, sardines');
      expect(items.map((i) => i.query), ['rice', 'eggs', 'sardines']);
    });

    test('reads quantities', () {
      expect(parseItems('2 x milk').single.quantity, 2);
      expect(parseItems('milk x3').single.quantity, 3);
      expect(parseItems('4 eggs').single.quantity, 4);
    });

    test('keeps sizes as part of the item', () {
      final item = parseItems('5 kg rice').single;
      expect(item.query, '5 kg rice');
      expect(item.quantity, 1);
    });

    test('merges repeats', () {
      expect(parseItems('Rice, rice').single.quantity, 2);
    });
  });

  test('draft adds raise quantity and stop at the limit', () {
    final draft = Draft()
      ..add(DraftItem(query: 'Rice'))
      ..add(DraftItem(query: 'rice', quantity: 2));
    expect(draft.items.single.quantity, 3);
    for (var i = 0; i < 40; i++) {
      draft.add(DraftItem(query: 'item $i'));
    }
    expect(draft.items.length, maxItems);
  });

  group('updates', () {
    test('compares versions as numbers', () {
      expect(isNewer('1.10.0', '1.9.0'), isTrue);
      expect(isNewer('1.0.0', '1.0.0'), isFalse);
      expect(isNewer('1.0.0', '1.0.1'), isFalse);
      expect(isNewer('2.0', '1.9.9'), isTrue);
    });

    test('offers only a newer release, with its notes', () async {
      final service = UpdateService(
        client: MockClient((_) async => http.Response(
              jsonEncode({'tag_name': 'v1.2.0', 'body': 'Faster search'}),
              200,
            )),
      );
      expect((await service.newerThan('1.1.0'))?.notes, 'Faster search');
      expect(await service.newerThan('1.2.0'), isNull);
    });

    test('a failed check stays silent', () async {
      final service = UpdateService(client: MockClient((_) async => http.Response('', 500)));
      expect(await service.newerThan('1.0.0'), isNull);
    });

    testWidgets('update notice shows what is new', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () => showUpdateAvailable(context, Release(version: '1.2.0', notes: 'Faster search'), '1.1.0'),
            child: const Text('open'),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      expect(find.text('Update available'), findsOneWidget);
      expect(find.text('Faster search'), findsOneWidget);
      expect(find.text('Download update'), findsOneWidget);
    });
  });

  group('calculator', () {
    CalculatorEngine run(String keys) {
      final engine = CalculatorEngine();
      keys.split('').forEach(engine.press);
      return engine;
    }

    test('adds, multiplies and chains', () {
      expect(run('12+8=').entry, '20');
      expect(run('21.5×3=').entry, '64.5');
      expect(run('10+5×2=').entry, '30');
    });

    test('division by zero shows an error', () {
      expect(run('5÷0=').entry, 'Error');
    });
  });

  test('duplicate copies items without ticks', () {
    final draft = Draft(name: 'Weekly', items: [DraftItem(query: 'rice', checked: true, customPrice: 40)]);
    final copy = draft.duplicate();
    expect(copy.name, 'Weekly copy');
    expect(copy.id, isNot(draft.id));
    expect(copy.items.single.checked, isFalse);
    expect(copy.items.single.customPrice, 40);
  });

  test('budget is remembered', () async {
    SharedPreferences.setMockInitialValues({});
    await AppState().setBudget(1500);
    final state = AppState();
    await state.loadBudget();
    expect(state.budget, 1500);
    await state.setBudget(null);
    await state.loadBudget();
    expect(state.budget, isNull);
  });

  test('peso formatting', () {
    expect(peso(1234.5), '₱1,234.50');
    expect(peso(8.24), '₱8.24');
  });

  test('drafts persist', () async {
    SharedPreferences.setMockInitialValues({});
    final store = DraftStore();
    await store.save(Draft(name: 'Weekly', items: [DraftItem(query: 'rice')]));
    final drafts = await store.read();
    expect(drafts.single.name, 'Weekly');
    await store.delete(drafts.single.id);
    expect(await store.read(), isEmpty);
  });

  testWidgets('prices show and live search filters them', (tester) async {
    await tester.pumpWidget(GroceryApp(state: fakeState()));
    await tester.pumpAndSettle();
    expect(find.text('Premium Rice, Local'), findsWidgets);

    await tester.enterText(find.byType(TextField).last, 'bear');
    await tester.pumpAndSettle();
    expect(find.text('Premium Rice, Local'), findsOneWidget); // Only the hero card.
    expect(find.text('₱50.00'), findsWidgets);

    await tester.enterText(find.byType(TextField).last, 'piatos');
    await tester.pumpAndSettle();
    expect(find.text('Found in stores'), findsOneWidget);
    expect(find.textContaining('Piatos Cheese'), findsOneWidget);

    await tester.enterText(find.byType(TextField).last, 'unicorn');
    await tester.pumpAndSettle();
    expect(find.textContaining('Nothing matches'), findsOneWidget);
  });

  testWidgets('layout adapts from phone to tablet', (tester) async {
    tester.view.physicalSize = const Size(1200, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(GroceryApp(state: fakeState()));
    await tester.pumpAndSettle();
    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
  });
}
