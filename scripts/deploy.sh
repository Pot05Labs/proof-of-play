#!/usr/bin/env bash
# Build the image, then deploy it only if the build succeeded, then wait until the new image is serving.
#   scripts/deploy.sh v7 loadtest [join] [judging]   (container: engagement | loadtest | watchalong)
#   judging = "judging" turns on the public read-only console and back-to-back matches at 10x
set -euo pipefail
TAG="${1:?image tag, e.g. v7}"; CONTAINER="${2:-watchalong}"; JOIN="${3:-30}"; MODE="${4:-}"
PUBLIC=false; LOOP=""
if [ "$MODE" = "judging" ]; then PUBLIC=true; LOOP=10; fi
RG=pop-hackathon-rg; ACR=popxjqzeluzrxqkoacr
cd "$(dirname "$0")/.."
git diff --quiet && git diff --cached --quiet || { echo "refusing: uncommitted changes"; exit 1; }
az acr build -r "$ACR" -t "proof-of-play:$TAG" --platform linux/amd64 .
set -a; . "$HOME/.config/proof-of-play/secrets.env"; set +a
az deployment group create -g "$RG" -n "pop-app-$TAG" -f infra/main.bicep -p prefix=pop \
  image="$ACR.azurecr.io/proof-of-play:$TAG" cosmosContainer="$CONTAINER" joinPerMinute="$JOIN" \
  adminKey="$POP_ADMIN_KEY" experimentSeed="$POP_EXPERIMENT_SEED" publicConsole="$PUBLIC" autoloopSpeed="$LOOP" --query properties.provisioningState -o tsv
REV=$(az containerapp show -g "$RG" -n pop-app --query properties.latestRevisionName -o tsv)
for _ in $(seq 1 60); do
  S=$(az containerapp revision show -g "$RG" -n pop-app --revision "$REV" --query properties.healthState -o tsv)
  [ "$S" = "Healthy" ] && { echo "deployed $TAG as $REV ($CONTAINER)"; exit 0; }
  sleep 10
done
echo "revision $REV did not become healthy"; exit 1
