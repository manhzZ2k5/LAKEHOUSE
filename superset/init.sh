#!/usr/bin/env bash
set -e

superset db upgrade

superset fab create-admin \
  --username "${SUPERSET_ADMIN_USER}" \
  --firstname "Admin" \
  --lastname "User" \
  --email "${SUPERSET_ADMIN_EMAIL}" \
  --password "${SUPERSET_ADMIN_PASSWORD}" || true

superset init

superset run -h 0.0.0.0 -p 8088
