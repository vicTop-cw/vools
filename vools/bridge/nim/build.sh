#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "Building Nim bridge libraries for Linux..."

# Linux/macOS: 输出到 lib/linux/
OUTDIR="../../lib/linux"

for nimfile in *.nim; do
    libname=$(basename "$nimfile" .nim)
    echo "Building libvools_bridge_${libname}.so ..."
    nim c --app:lib --out:"${OUTDIR}/libvools_bridge_${libname}.so" "$nimfile"
done

echo "Done! Libraries built in ${OUTDIR}/"
