import 'package:flutter/material.dart';

import '../drafts.dart';
import '../state.dart';
import 'list_editor.dart';

class MultiScreen extends StatefulWidget {
  const MultiScreen({super.key});

  @override
  State<MultiScreen> createState() => _MultiScreenState();
}

class _MultiScreenState extends State<MultiScreen> {
  Draft _draft = Draft();

  Future<void> _save() async {
    final messenger = ScaffoldMessenger.of(context);
    if (_draft.name.isEmpty) _draft.name = 'My list';
    await AppScope.of(context).drafts.save(_draft);
    messenger.showSnackBar(const SnackBar(content: Text('Saved to Drafts')));
    setState(() => _draft = Draft());
  }

  @override
  Widget build(BuildContext context) {
    return ListView(padding: const EdgeInsets.all(16), children: [
      Text('Search multiple items', style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 4),
      const Text('One item per line, or separate with commas.'),
      const SizedBox(height: 12),
      ListEditor(
        key: ValueKey(_draft.id),
        draft: _draft,
        onChanged: () => setState(() {}),
        footer: OutlinedButton(onPressed: _save, child: const Text('Save as draft')),
      ),
    ]);
  }
}
