#!/bin/sh
# Xcode build phase: put Python, our code and its packages into the app bundle.
#   python/        the standard library (from Python.xcframework)
#   app/           src/sphero_dev, plus the files ask.py reads
#   app_packages/  spherov2 and certifi (from scripts/fetch-python.sh)
set -eu
cd "$PROJECT_DIR"
XCF=Frameworks/Python.xcframework
[ -d "$XCF" ] || { echo "error: $XCF is missing; run ios/scripts/fetch-python.sh" >&2; exit 1; }
[ -d Build/app_packages ] || { echo "error: run ios/scripts/fetch-python.sh" >&2; exit 1; }

DEST="$CODESIGNING_FOLDER_PATH"
rm -rf "$DEST/app" "$DEST/app_packages"
mkdir -p "$DEST/app"
cp -R ../src/sphero_dev "$DEST/app/"
cp ../docs/api-reference.md "$DEST/app/sphero_dev/api-reference.md"
cp ../examples/edu_app/square.py "$DEST/app/sphero_dev/example_square.py"
cp -R Build/app_packages "$DEST/app_packages"
find "$DEST/app" "$DEST/app_packages" -name __pycache__ -prune -exec rm -rf {} +

# Python-Apple-support's helper copies the standard library for this platform
# (device or simulator) to $DEST/python and turns its binary modules into the
# signed frameworks iOS requires. Its file name has varied between releases.
for f in "$XCF/build/utils.sh" "$XCF/build/build_utils.sh"; do
  [ -f "$f" ] && UTILS=$f
done
[ -n "${UTILS:-}" ] || { echo "error: no build utils in $XCF/build" >&2; exit 1; }
# shellcheck disable=SC1090
. "$UTILS"
install_python "$XCF" app app_packages
