#!/bin/sh
# Run once on the Mac before the first build (and to update Python):
#   1. downloads BeeWare's Python.xcframework (CPython for iOS) into Frameworks/
#   2. installs the app's pure-Python packages (spherov2, certifi) into Build/app_packages
set -eu
cd "$(dirname "$0")/.."

# The newest 3.13 release of beeware/Python-Apple-support with an iOS build.
url=$(curl -fsSL "https://api.github.com/repos/beeware/Python-Apple-support/releases?per_page=30" |
  python3 -c '
import json, sys
for rel in json.load(sys.stdin):
    if rel["tag_name"].startswith("3.13-"):
        for a in rel["assets"]:
            if "iOS-support" in a["name"] and a["name"].endswith(".tar.gz"):
                print(a["browser_download_url"]); sys.exit()
sys.exit("no 3.13 iOS support release found")')
echo "Downloading $url"
rm -rf Frameworks/Python.xcframework && mkdir -p Frameworks
curl -fsSL "$url" | tar -xz -C Frameworks
[ -d Frameworks/Python.xcframework ] || { echo "no Python.xcframework in the download" >&2; exit 1; }

# Pure-Python only: anything with compiled code would need an iOS build.
rm -rf Build/app_packages && mkdir -p Build
python3 -m pip install --quiet --no-deps --only-binary=:all: --target Build/app_packages \
  "spherov2>=0.12" certifi
if find Build/app_packages -name '*.so' | grep -q .; then
  echo "app_packages contains compiled modules; they won't load on iOS" >&2
  exit 1
fi
echo "Ready: Frameworks/Python.xcframework and Build/app_packages"
