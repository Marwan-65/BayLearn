#!/usr/bin/env bash

#safety flags for bash
#-e exit if any command fails
# -u treat unset variables as errors and exit
# -o pipefail if any command in a pipeline (cmd1 | cmd2) fails, the whole pipeline fails (not just the last command)
set -euo pipefail

#$n is the nth passed variable
#:- value means use that value as default if argument not passed
SCH="${1:-2}"
Q="${2:-3}"
INPUT="${3:-processes.txt}"

cd /workspace

make build #produce the process_generator.out binary
# Stop any existing scheduler container to ensure a clean state (ignore errors if it doesn't exist)
make stop || true

cd scheduler
touch keyfile

# The scheduler intentionally terminates via SIGINT on process-group cleanup.
# Ignore INT in this wrapper so post-processing still runs.
trap '' INT
./process_generator.out "$INPUT" -sch "$SCH" -q "$Q" || true

cd /workspace
python3 scripts/log_to_json.py -sch "$SCH" -q "$Q"
