#!/usr/bin/env bash
set -euo pipefail

PROJECT="sl33p-space"
REGION="europe-west1"
SERVICE="sl33p-space"
REPO="sl33p-space"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/${SERVICE}"

echo "=== sl33p-space deploy ==="
echo "  Project:  ${PROJECT}"
echo "  Region:   ${REGION}"
echo "  Service:  ${SERVICE}"
echo ""

# ── 1. Ensure Artifact Registry repo exists ──
if ! gcloud artifacts repositories describe "${REPO}" \
      --location="${REGION}" --project="${PROJECT}" &>/dev/null; then
  echo "[1/4] Creating Artifact Registry repo..."
  gcloud artifacts repositories create "${REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${PROJECT}" \
    --description="sl33p-space container images"

  # Cleanup policy: keep only 2 most recent images
  gcloud artifacts repositories set-cleanup-policies "${REPO}" \
    --location="${REGION}" \
    --project="${PROJECT}" \
    --policy=<(cat <<'POLICY'
[
  {
    "name": "keep-recent-2",
    "action": {"type": "Keep"},
    "mostRecentVersions": {
      "keepCount": 2
    }
  },
  {
    "name": "delete-old",
    "action": {"type": "Delete"},
    "condition": {
      "tagState": "ANY",
      "olderThan": "86400s"
    }
  }
]
POLICY
)
else
  echo "[1/4] Artifact Registry repo exists"
fi

# ── 2. Build and push ──
echo "[2/4] Building container image..."
gcloud builds submit \
  --tag "${IMAGE}:latest" \
  --project="${PROJECT}" \
  --timeout=600

# ── 3. Deploy to Cloud Run ──
echo "[3/4] Deploying to Cloud Run..."
gcloud run deploy "${SERVICE}" \
  --image="${IMAGE}:latest" \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --memory=2Gi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --timeout=300 \
  --update-env-vars="FIREBASE_PROJECT_ID=${PROJECT},FIREBASE_API_KEY=${FIREBASE_API_KEY},FIREBASE_AUTH_DOMAIN=${PROJECT}.firebaseapp.com,FIREBASE_APP_ID=${FIREBASE_APP_ID},GCS_BUCKET=${GCS_BUCKET:-sl33p-space-music},SERVICE_URL=https://sl33p-space-lqs3sot4na-ew.a.run.app" \
  --update-secrets="GOOGLE_API_KEY=google-api-key:latest,MONGODB_URI=mongodb-uri:latest,FLASK_SECRET_KEY=flask-secret-key:latest,/tmp/sl33p-mongo-cert.pem=mongodb-cert:latest"

# ── 4. Show URL ──
echo ""
echo "[4/4] Done!"
URL=$(gcloud run services describe "${SERVICE}" \
  --region="${REGION}" --project="${PROJECT}" \
  --format="value(status.url)")
echo "  Live at: ${URL}"
