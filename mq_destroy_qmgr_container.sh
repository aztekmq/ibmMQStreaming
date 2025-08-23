#!/bin/bash
# =============================================================================
# Script Name : mq_destroy_qmgr_container.sh
# Description : Lists Docker containers and prompts the user to select ones to
#               delete.
# Author      : rob lee
# Maintainer  : rob@aztekmq.net
# Version     : 1.0.0
# Created     : 2025-04-14
# Last Update : 2025-08-19
# License     : MIT (SPDX-License-Identifier: MIT)
#
# Standards & Conventions:
#   - Dates use ISO 8601 (YYYY-MM-DD).
#   - Shell is Bash using POSIX-compatible patterns where practical.
#   - External tools: Docker Engine.
#   - Documentation language uses RFC 2119 keywords (MUST/SHOULD/MAY).
#   - Container metadata aligns with OCI/Docker Compose format 3.8.
#
# Usage:
#   ./mq_destroy_qmgr_container.sh
#
# Behavior Summary:
#   1) Lists existing Docker containers.
#   2) Prompts the user to choose containers to delete.
#   3) Removes the selected containers using 'docker rm -f'.
#
# Exit Codes:
#   0  Successful completion or no containers selected.
#   1  Errors from docker commands.
#
# Dependencies (Informational):
#   - docker (Engine CLI)
#
# Shell Quality:
#   - This script intentionally avoids 'set -euo pipefail' to preserve original
#     behavior. If you adopt it, test thoroughly in your environment.
#   - Recommended linting with ShellCheck: https://www.shellcheck.net/
# =============================================================================

# --------- COLORS ---------
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
NC="\033[0m" # No Color

# --------- List Containers ---------
echo -e "${CYAN}🔍 Gathering container list...${NC}"
mapfile -t CONTAINERS < <(docker ps -a --format '{{.Names}}')

if [[ ${#CONTAINERS[@]} -eq 0 ]]; then
  echo -e "${YELLOW}No containers found. Nothing to do.${NC}"
  exit 0
fi

echo -e "${CYAN}Available containers:${NC}"
for i in "${!CONTAINERS[@]}"; do
  printf "%3d) %s\n" $((i+1)) "${CONTAINERS[i]}"
done

echo ""
read -p "Enter numbers to delete (e.g., 1 2 3) or 'all' to delete all: " -r SELECTION

TARGETS=()
if [[ "$SELECTION" == "all" ]]; then
  TARGETS=("${CONTAINERS[@]}")
else
  for NUM in $SELECTION; do
    if [[ "$NUM" =~ ^[0-9]+$ ]] && (( NUM >= 1 && NUM <= ${#CONTAINERS[@]} )); then
      TARGETS+=("${CONTAINERS[NUM-1]}")
    fi
  done
fi

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo -e "${YELLOW}No containers selected. Exiting.${NC}"
  exit 0
fi

echo -e "${RED}Deleting: ${TARGETS[*]}${NC}"
if docker rm -f "${TARGETS[@]}"; then
  echo -e "${GREEN}✅ Deletion complete.${NC}"
else
  echo -e "${RED}❌ Deletion encountered errors.${NC}"
  exit 1
fi

# =============================================================================
# End of file
# =============================================================================
