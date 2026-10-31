#!/usr/bin/env bash
# Generates the Android (Kotlin) and iOS (Swift) host projects from the current Flutter
# template, so only the shared app code lives in the repository.
set -euo pipefail
platform="$1"

flutter create --org com.groceryprice --project-name grocery_price_finder --platforms android,ios --android-language kotlin --ios-language swift .
rm -f test/widget_test.dart  # The template test targets a demo app that does not exist here.

if [ "$platform" = "android" ]; then
  manifest=android/app/src/main/AndroidManifest.xml
  sed -i '/<manifest /a\    <uses-permission android:name="android.permission.INTERNET" />\n    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />\n    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />' "$manifest"
  sed -i 's/android:label="grocery_price_finder"/android:label="Grocery Price Finder"/' "$manifest"
else
  plist=ios/Runner/Info.plist
  /usr/libexec/PlistBuddy -c "Add :NSLocationWhenInUseUsageDescription string 'Finds your city so the app can show the official prices and stores that apply to you.'" "$plist"
  /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 'Grocery Price Finder'" "$plist"
  /usr/libexec/PlistBuddy -c "Add :NSCameraUsageDescription string 'Take a photo of a receipt or shelf tag as proof of a price.'" "$plist"
  /usr/libexec/PlistBuddy -c "Add :NSPhotoLibraryUsageDescription string 'Choose a photo of a receipt or shelf tag as proof of a price.'" "$plist"
fi

flutter pub get
dart run flutter_launcher_icons
