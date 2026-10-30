import 'package:flutter/material.dart';

import 'screens/drafts_screen.dart';
import 'screens/multi_screen.dart';
import 'screens/prices_screen.dart';
import 'state.dart';
import 'updates.dart';

void main() => runApp(const GroceryApp());

class GroceryApp extends StatelessWidget {
  const GroceryApp({super.key, this.state});

  final AppState? state;

  @override
  Widget build(BuildContext context) {
    return AppScope(
      state: state ?? AppState(),
      child: MaterialApp(
        title: 'Grocery Price Finder',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF14532D)),
          scaffoldBackgroundColor: const Color(0xFFFAF8F2),
          useMaterial3: true,
        ),
        home: const HomeShell(),
      ),
    );
  }
}

/// Bottom tabs on phones, a side rail on tablets and landscape screens.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _tab = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) runUpdateChecks(context);
    });
  }

  static const _pages = [PricesScreen(), MultiScreen(), DraftsScreen()];

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 700;
    final page = SafeArea(child: IndexedStack(index: _tab, children: _pages));
    if (wide) {
      return Scaffold(
        body: Row(children: [
          NavigationRail(
            selectedIndex: _tab,
            labelType: NavigationRailLabelType.all,
            onDestinationSelected: (i) => setState(() => _tab = i),
            destinations: const [
              NavigationRailDestination(icon: Icon(Icons.sell_outlined), label: Text('Prices')),
              NavigationRailDestination(icon: Icon(Icons.checklist), label: Text('Multi search')),
              NavigationRailDestination(icon: Icon(Icons.edit_note), label: Text('Drafts')),
            ],
          ),
          Expanded(child: page),
        ]),
      );
    }
    return Scaffold(
      body: page,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.sell_outlined), label: 'Prices'),
          NavigationDestination(icon: Icon(Icons.checklist), label: 'Multi search'),
          NavigationDestination(icon: Icon(Icons.edit_note), label: 'Drafts'),
        ],
      ),
    );
  }
}
