#!/usr/bin/env bash
# Re-pin every gyopart-scraper image in a values file to the digest :latest has on Docker Hub.
# Run after `docker compose push scraper-...`, then commit + push the values file. Pinning by
# digest is what lets scrape-job-manager notice a new image and retest suspended jobs; a bare
# :latest never changes as far as the operator can tell.
#   scripts/pin-scraper-images.sh [helm/gyopart/values-dev.yaml]
set -euo pipefail
VALUES=${1:-helm/gyopart/values-dev.yaml}
repos=$(grep -oE 'dwilson2547/gyopart-scraper-[a-z0-9-]+' "$VALUES" | sort -u)
for repo in $repos; do
  digest=$(docker buildx imagetools inspect "$repo:latest" | awk '/^Digest:/ {print $2; exit}')
  [[ $digest == sha256:* ]] || { echo "no digest for $repo:latest" >&2; exit 1; }
  sed -i -E "s#(image: )${repo}(:latest|@sha256:[0-9a-f]+)#\1${repo}@${digest}#" "$VALUES"
  echo "$repo@$digest"
done
