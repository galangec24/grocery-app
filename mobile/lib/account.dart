import 'package:flutter/material.dart';

import 'api.dart';
import 'state.dart';

/// Shows sign in or registration. Returns true when the shopper is signed in.
Future<bool> askToSignIn(BuildContext context) async {
  final done = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    builder: (_) => const _AccountSheet(),
  );
  return done ?? false;
}

class _AccountSheet extends StatefulWidget {
  const _AccountSheet();

  @override
  State<_AccountSheet> createState() => _AccountSheetState();
}

class _AccountSheetState extends State<_AccountSheet> {
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _register = true;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final state = AppScope.of(context);
    final navigator = Navigator.of(context);
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await state.signIn(_email.text.trim(), _password.text, name: _register ? _name.text.trim() : null);
      navigator.pop(true);
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = error.message;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(_register ? 'Join the price community' : 'Welcome back', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 4),
        const Text('Sign in to share what you paid. Lists and drafts work without an account.'),
        const SizedBox(height: 12),
        if (_register)
          TextField(controller: _name, decoration: const InputDecoration(labelText: 'Your name')),
        TextField(
          controller: _email,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(labelText: 'Email'),
        ),
        TextField(
          controller: _password,
          obscureText: true,
          decoration: InputDecoration(labelText: 'Password', helperText: _register ? 'At least 10 characters' : null),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        const SizedBox(height: 14),
        FilledButton(onPressed: _busy ? null : _submit, child: Text(_register ? 'Create account' : 'Sign in')),
        TextButton(
          onPressed: () => setState(() {
            _register = !_register;
            _error = null;
          }),
          child: Text(_register ? 'Already have an account? Sign in' : 'New here? Create an account'),
        ),
      ]),
    );
  }
}
