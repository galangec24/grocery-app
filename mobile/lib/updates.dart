import 'dart:convert';
import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

const _repo = 'galangec24/grocery-app';
const _seenKey = 'last_seen_version';
const apkUrl = 'https://github.com/$_repo/releases/latest/download/grocery-price-finder.apk';

class Release {
  Release({required this.version, required this.notes});

  factory Release.fromJson(Map<String, dynamic> json) => Release(
        version: (json['tag_name'] as String).replaceFirst(RegExp('^v'), ''),
        notes: ((json['body'] as String?) ?? '').trim(),
      );

  final String version;
  final String notes;
}

/// True when [candidate] is newer than [current], comparing numbers: 1.10.0 > 1.9.0.
bool isNewer(String candidate, String current) {
  List<int> parts(String v) =>
      v.split('.').map((p) => int.tryParse(p.split(RegExp(r'[-+]')).first) ?? 0).toList();
  final a = parts(candidate);
  final b = parts(current);
  for (var i = 0; i < 3; i++) {
    final x = i < a.length ? a[i] : 0;
    final y = i < b.length ? b[i] : 0;
    if (x != y) return x > y;
  }
  return false;
}

class UpdateService {
  UpdateService({http.Client? client}) : _client = client ?? http.Client();
  final http.Client _client;

  Future<Release?> _fetch(String path) async {
    try {
      final response = await _client
          .get(Uri.parse('https://api.github.com/repos/$_repo/releases/$path'),
              headers: {'Accept': 'application/vnd.github+json'})
          .timeout(const Duration(seconds: 15));
      if (response.statusCode != 200) return null;
      return Release.fromJson(jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>);
    } catch (_) {
      return null; // An update check must never get in the shopper's way.
    }
  }

  Future<Release?> newerThan(String current) async {
    final latest = await _fetch('latest');
    return latest != null && isNewer(latest.version, current) ? latest : null;
  }

  Future<Release?> notesFor(String version) => _fetch('tags/v$version');
}

/// Shows "What's new" once after an update, then offers any newer release.
/// Android only: iPhones update through the App Store.
Future<void> runUpdateChecks(BuildContext context, {UpdateService? service}) async {
  if (!Platform.isAndroid) return;
  final updates = service ?? UpdateService();
  final installed = (await PackageInfo.fromPlatform()).version;
  final prefs = await SharedPreferences.getInstance();
  final seen = prefs.getString(_seenKey);
  await prefs.setString(_seenKey, installed);

  if (seen != null && seen != installed) {
    final notes = await updates.notesFor(installed);
    if (notes != null && context.mounted) {
      await showWhatsNew(context, notes);
    }
  }
  final newer = await updates.newerThan(installed);
  if (newer != null && context.mounted) {
    await showUpdateAvailable(context, newer, installed);
  }
}

Future<void> showWhatsNew(BuildContext context, Release release) {
  return showDialog<void>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text("What's new in ${release.version}"),
      content: SingleChildScrollView(
        child: Text(release.notes.isEmpty ? 'Improvements and fixes.' : release.notes),
      ),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Got it'))],
    ),
  );
}

Future<void> showUpdateAvailable(BuildContext context, Release release, String installed) {
  return showDialog<void>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Update available'),
      content: SingleChildScrollView(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
          Text('Version ${release.version} is ready. You have $installed.'),
          if (release.notes.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text("What's new", style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 4),
            Text(release.notes),
          ],
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Later')),
        FilledButton(
          onPressed: () {
            Navigator.pop(context);
            launchUrl(Uri.parse(apkUrl), mode: LaunchMode.externalApplication);
          },
          child: const Text('Download update'),
        ),
      ],
    ),
  );
}
