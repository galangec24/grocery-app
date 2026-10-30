import 'package:flutter/material.dart';

import '../drafts.dart';
import '../state.dart';
import '../widgets.dart';
import 'list_editor.dart';

class DraftsScreen extends StatefulWidget {
  const DraftsScreen({super.key});

  @override
  State<DraftsScreen> createState() => _DraftsScreenState();
}

class _DraftsScreenState extends State<DraftsScreen> {
  List<Draft>? _drafts;

  Future<void> _load() async {
    final drafts = await AppScope.of(context).drafts.read();
    if (mounted) setState(() => _drafts = drafts);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_drafts == null) _load();
  }

  Future<void> _open(Draft draft) async {
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => DraftPage(draft: draft)));
    _load();
  }

  Future<void> _delete(Draft draft) async {
    final store = AppScope.of(context).drafts;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Delete ${draft.name.isEmpty ? 'this draft' : draft.name}?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Delete')),
        ],
      ),
    );
    if (confirmed == true) {
      await store.delete(draft.id);
      _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    final drafts = _drafts ?? const <Draft>[];
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(padding: const EdgeInsets.all(16), children: [
        Text('Drafts', style: Theme.of(context).textTheme.headlineSmall),
        const Text('Lists you\'re still working on. Saved on this device only.'),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: () => _open(Draft()),
          icon: const Icon(Icons.add),
          label: const Text('New draft'),
        ),
        const SizedBox(height: 8),
        if (_drafts != null && drafts.isEmpty)
          const Message(text: 'No drafts yet. Start one, or save a list from Multi search.'),
        for (final draft in drafts)
          Card3d(
            margin: const EdgeInsets.only(top: 10),
            padding: 4,
            child: ListTile(
              title: Text(draft.name.isEmpty ? 'Untitled draft' : draft.name),
              subtitle: Text('${draft.items.length} ${draft.items.length == 1 ? 'item' : 'items'}'),
              onTap: () => _open(draft),
              trailing: IconButton(
                tooltip: 'Delete',
                onPressed: () => _delete(draft),
                icon: const Icon(Icons.delete_outline),
              ),
            ),
          ),
      ]),
    );
  }
}

class DraftPage extends StatefulWidget {
  const DraftPage({super.key, required this.draft});

  final Draft draft;

  @override
  State<DraftPage> createState() => _DraftPageState();
}

class _DraftPageState extends State<DraftPage> {
  late final _name = TextEditingController(text: widget.draft.name);

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  void _save() {
    setState(() {});
    AppScope.of(context).drafts.save(widget.draft);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Draft')),
      body: SafeArea(
        child: ListView(padding: const EdgeInsets.all(16), children: [
          TextField(
            controller: _name,
            style: Theme.of(context).textTheme.titleLarge,
            decoration: const InputDecoration(hintText: 'Name this draft'),
            onChanged: (value) {
              widget.draft.name = value;
              _save();
            },
          ),
          const SizedBox(height: 12),
          ListEditor(draft: widget.draft, onChanged: _save),
        ]),
      ),
    );
  }
}
