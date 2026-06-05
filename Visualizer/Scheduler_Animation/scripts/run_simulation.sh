#!/usr/bin/env bash
set -euo pipefail

SCH="${1:-2}"
Q="${2:-3}"
INPUT="${3:-processes.txt}"

cd /workspace

make build
make stop || true

cd scheduler
touch keyfile

# The scheduler intentionally terminates via SIGINT on process-group cleanup.
# Ignore INT in this wrapper so post-processing still runs.
trap '' INT
./process_generator.out "$INPUT" -sch "$SCH" -q "$Q" || true

cd /workspace
python3 scripts/log_to_json.py -sch "$SCH" -q "$Q"
