#!/bin/sh
set -e
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc mb -p "local/${MINIO_BUCKET:-moozika-scores}" || true
mc anonymous set none "local/${MINIO_BUCKET:-moozika-scores}" || true
echo "MinIO bucket ready: ${MINIO_BUCKET:-moozika-scores}"
