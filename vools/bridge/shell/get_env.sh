#!/bin/bash
if [ $# -eq 0 ]; then
    echo ""
    exit 1
fi
printenv "$1" 2>/dev/null || echo ""