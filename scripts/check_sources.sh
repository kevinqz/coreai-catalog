#!/usr/bin/env bash
# Core AI Catalog — Source Watchdog
# Checks GitHub repos and HuggingFace accounts for new Core AI models/artifacts.
# Run by Hermes cron 2x/day. Stays SILENT when nothing changes (watchdog pattern).
#
# Exit codes: 0 = checked (may or may not have output), non-zero = error alert.

set -euo pipefail

CATALOG_DIR="/Users/kevinsaltarelli/Dev/Github/coreai-catalog"
STATE_FILE="$CATALOG_DIR/.source-watch-state.json"
REPORT=""

# ── Load or init state ──────────────────────────────────────────────────
if [[ -f "$STATE_FILE" ]]; then
  LAST_RUN=$(jq -r '.last_run // empty' "$STATE_FILE" 2>/dev/null || echo "")
else
  LAST_RUN=""
fi

NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Default lookback: 48h (covers 2x/day schedule with margin)
SINCE=${LAST_RUN:-$(date -u -v-48H +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d "48 hours ago" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "")}

# ── Current catalog baseline ────────────────────────────────────────────
KNOWN_MODELS=$(grep -cE '^- id:' "$CATALOG_DIR/catalog.yaml" 2>/dev/null || echo "0")
if [[ "$KNOWN_MODELS" == "0" ]]; then
  KNOWN_MODELS=$(grep -cE '^  - id:' "$CATALOG_DIR/catalog.yaml" 2>/dev/null || echo "0")
fi

# ── GitHub repos to monitor ─────────────────────────────────────────────
GH_REPOS=(
  "john-rocky/coreai-model-zoo"
  "apple/coreai-models"
  "john-rocky/apple-silicon-llm-bench"
  "john-rocky/coreai-samples"
  "gafiatulin/vibevoice-coreai"
  "mweinbach/NemotronCoreAI"
)

# ── HuggingFace accounts to monitor ─────────────────────────────────────
HF_ACCOUNTS=(
  "mlboydaisuke"
  "CarstenL"
  "Intiser"
  "warshanks"
  "bryanbblewis11"
  "lenitas"
)

# ── Key upstream model orgs (HF) ────────────────────────────────────────
HF_ORGS=(
  "Qwen"
  "google"
  "openai"
  "mistralai"
  "ibm-granite"
  "LiquidAI"
  "openbmb"
  "black-forest-labs"
)

CHANGES_FOUND=0

# ════════════════════════════════════════════════════════════════════════
# 1. GITHUB: check recent commits in key repos
# ════════════════════════════════════════════════════════════════════════
for repo in "${GH_REPOS[@]}"; do
  # Fetch commits since last run (max 10)
  commits_json=$(curl -sf --max-time 15 \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${repo}/commits?since=${SINCE}&per_page=10" 2>/dev/null) || continue

  commit_count=$(echo "$commits_json" | jq 'length' 2>/dev/null || echo "0")

  if [[ "$commit_count" != "0" && "$commit_count" -gt 0 ]]; then
    CHANGES_FOUND=1
    REPORT+="🔔 **GitHub: ${repo}** — ${commit_count} novo(s) commit(s):\n"
    echo "$commits_json" | jq -r '.[] | "   • \(.sha[0:7]) \(.commit.message | split("\n")[0]) (\(.commit.author.date))"' 2>/dev/null >> /tmp/coreai_commits.txt
    while IFS= read -r line; do
      REPORT+="${line}\n"
    done < /tmp/coreai_commits.txt
    rm -f /tmp/coreai_commits.txt
    REPORT+="\n"
  fi
done

# ════════════════════════════════════════════════════════════════════════
# 2. HUGGINGFACE: check for new models in Core AI artifact accounts
# ════════════════════════════════════════════════════════════════════════
for account in "${HF_ACCOUNTS[@]}"; do
  models_json=$(curl -sf --max-time 15 \
    "https://huggingface.co/api/models?author=${account}&sort=lastModified&direction=-1&limit=50" 2>/dev/null) || continue

  # Filter models modified since our lookback
  recent=$(echo "$models_json" | jq --arg since "$SINCE" \
    '[.[] | select(.lastModified > $since)] | length' 2>/dev/null || echo "0")

  if [[ "$recent" != "0" && "$recent" -gt 0 ]]; then
    CHANGES_FOUND=1
    REPORT+="🔔 **HuggingFace: ${account}** — ${recent} modelo(s) atualizado(s):\n"
    new_models=$(echo "$models_json" | jq --arg since "$SINCE" -r \
      '.[] | select(.lastModified > $since) | "   • \(.id) (mod: \(.lastModified))"' 2>/dev/null)
    while IFS= read -r line; do
      REPORT+="${line}\n"
    done <<< "$new_models"
    REPORT+="\n"
  fi
done

# ════════════════════════════════════════════════════════════════════════
# 3. HUGGINGFACE: check upstream orgs for new models (potential Core AI candidates)
# ════════════════════════════════════════════════════════════════════════
for org in "${HF_ORGS[@]}"; do
  models_json=$(curl -sf --max-time 15 \
    "https://huggingface.co/api/models?author=${org}&sort=lastModified&direction=-1&limit=5" 2>/dev/null) || continue

  recent=$(echo "$models_json" | jq --arg since "$SINCE" \
    '[.[] | select(.lastModified > $since)] | length' 2>/dev/null || echo "0")

  if [[ "$recent" != "0" && "$recent" -gt 0 ]]; then
    CHANGES_FOUND=1
    REPORT+="🔔 **HF Upstream: ${org}** — ${recent} modelo(s) novo(s)/atualizado(s):\n"
    new_models=$(echo "$models_json" | jq --arg since "$SINCE" -r \
      '.[] | select(.lastModified > $since) | "   • \(.id) (mod: \(.lastModified))"' 2>/dev/null)
    while IFS= read -r line; do
      REPORT+="${line}\n"
    done <<< "$new_models"
    REPORT+="\n"
  fi
done

# ════════════════════════════════════════════════════════════════════════
# 4. CORE AI MODEL ZOO: check for new model directories
# ════════════════════════════════════════════════════════════════════════
zoo_tree=$(curl -sf --max-time 15 \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/john-rocky/coreai-model-zoo/git/trees/main?recursive=1" 2>/dev/null) || zoo_tree=""

if [[ -n "$zoo_tree" ]]; then
  # Count model directories under zoo/ and official/
  zoo_models=$(echo "$zoo_tree" | jq -r '.tree[].path' 2>/dev/null | grep -cE '^zoo/[^/]+/$' || echo 0)
  official_models=$(echo "$zoo_tree" | jq -r '.tree[].path' 2>/dev/null | grep -cE '^official/[^/]+/$' || echo 0)
  # Clean up any stray whitespace/newlines
  zoo_models=$(echo "$zoo_models" | tr -d '[:space:]')
  official_models=$(echo "$official_models" | tr -d '[:space:]')
  [[ -z "$zoo_models" ]] && zoo_models=0
  [[ -z "$official_models" ]] && official_models=0
  total_tree=$((zoo_models + official_models))
  if [[ "$total_tree" -gt "$KNOWN_MODELS" ]]; then
    diff=$((total_tree - KNOWN_MODELS))
    CHANGES_FOUND=1
    REPORT+="🔔 **Core AI Model Zoo** — árvore tem ${total_tree} diretórios de modelo vs ${KNOWN_MODELS} no catálogo (+${diff} potencialmente novos)\n\n"
  fi
fi

# ════════════════════════════════════════════════════════════════════════
# OUTPUT
# ════════════════════════════════════════════════════════════════════════

# Save state
echo "{\"last_run\": \"${NOW_ISO}\"}" > "$STATE_FILE"

if [[ "$CHANGES_FOUND" -eq 1 ]]; then
  echo "🔍 **Core AI Catalog — Monitor de Fontes**"
  echo "Período: ${SINCE} → ${NOW_ISO}"
  echo "Catálogo atual: ${KNOWN_MODELS} modelos"
  echo ""
  printf '%b' "$REPORT"
  echo "---"
  echo "⚡ Revisar findings e atualizar catalog.yaml se necessário."
else
  # Silent — no changes detected
  :
fi
