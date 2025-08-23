#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# File      : configure_mq.sh
# Purpose   : Apply demo MQSC into a running IBM MQ container using runmqsc.
# Author    : rob lee
# Version   : 1.1.0
# License   : MIT (SPDX-License-Identifier: MIT)
# Requirements:
#   - Docker CLI available and user permitted to exec in target container.
#   - A running MQ container exposing runmqsc for the target queue manager.
# Usage:
#   ./configure_mq.sh [--qmgr QM1] [--container qm1] [--mqsc /path/to/file.mqsc]
# Exit Codes:
#   0  Success
#   2  MQSC file not found
#   1  Other error
# Notes:
#   - Script is idempotent when MQSC uses REPLACE.
#   - Follows POSIX shell best practices (set -euo pipefail).
# -----------------------------------------------------------------------------
set -euo pipefail

QMGR="QM1"
CONTAINER="qm1"
MQSC_FILE="$(dirname "$0")/../mqsc/10-streaming-demo.mqsc"

usage() {
  echo "Usage: $0 [--qmgr QM1] [--container qm1] [--mqsc /path/to/file.mqsc]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --qmgr) QMGR="$2"; shift 2;;
    --container) CONTAINER="$2"; shift 2;;
    --mqsc) MQSC_FILE="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

if [[ ! -f "$MQSC_FILE" ]]; then
  echo "MQSC file not found: $MQSC_FILE" >&2
  exit 2
fi

echo "Applying MQSC to $QMGR on container $CONTAINER ..."
docker exec -i "$CONTAINER" bash -lc "runmqsc $QMGR" < "$MQSC_FILE"

echo "Done."
echo "Verify with:"
echo "  docker exec -it $CONTAINER runmqsc $QMGR <<<'DISPLAY QLOCAL(*) STREAMQ STRMQOS'"