#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/setup_minio_bucket.sh [ALIAS] [ENDPOINT] [ACCESS_KEY] [SECRET_KEY] [BUCKET]
# Defaults: local http://localhost:9100 myuser mystrongpassword123 designia

ALIAS="${1:-local}"
ENDPOINT="${2:-http://localhost:9100}"
ACCESS_KEY="${3:-myuser}"
SECRET_KEY="${4:-mystrongpassword123}"
BUCKET="${5:-designia}"

command -v mc >/dev/null 2>&1 || { echo "MinIO client 'mc' is required"; exit 1; }

echo "Configuring MinIO alias '${ALIAS}' -> ${ENDPOINT}"
mc alias set "${ALIAS}" "${ENDPOINT}" "${ACCESS_KEY}" "${SECRET_KEY}" >/dev/null

echo "Creating bucket if missing: ${ALIAS}/${BUCKET}"
mc mb "${ALIAS}/${BUCKET}" || true

echo "Setting public read (download) policy"
mc anonymous set download "${ALIAS}/${BUCKET}"

echo "Applying CORS rules"
TMP_CORS_JSON=$(mktemp)
# Build AllowedOrigins from FRONTEND_URL if present, plus common localhost ports
FRONTEND_URL_ENV="${FRONTEND_URL:-}"
if [ -n "$FRONTEND_URL_ENV" ]; then
  ORIGINS_JSON="\"$FRONTEND_URL_ENV\", \"http://localhost:5173\", \"http://127.0.0.1:5173\", \"http://localhost:5174\", \"http://127.0.0.1:5174\""
else
  ORIGINS_JSON="\"http://localhost:5173\", \"http://127.0.0.1:5173\", \"http://localhost:5174\", \"http://127.0.0.1:5174\""
fi

cat >"${TMP_CORS_JSON}" <<JSON
[
  {
    "AllowedOrigins": [${ORIGINS_JSON}],
    "AllowedMethods": ["GET", "POST", "PUT"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag", "x-amz-request-id", "x-amz-id-2"],
    "MaxAgeSeconds": 3000
  }
]
JSON
mc cors set "${ALIAS}/${BUCKET}" "${TMP_CORS_JSON}"
mc cors info "${ALIAS}/${BUCKET}"

echo "Done. Example public URL: ${ENDPOINT%/}/${BUCKET}/path/to/object.jpg"
