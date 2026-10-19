#!/usr/bin/env bash
# ==============================================================================
# AURA AGENTIC SYSTEM: Automated PostgreSQL Backup Script
# Creates compressed, checksum-verified backups with automatic rotation
# ==============================================================================

set -euo pipefail

# Configuration with environment defaults
BACKUP_DIR="${BACKUP_DIR:-./backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-aura_db}"
POSTGRES_USER="${POSTGRES_USER:-aura_user}"

mkdir -p "${BACKUP_DIR}"

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
BACKUP_FILE="${BACKUP_DIR}/${POSTGRES_DB}_${TIMESTAMP}.dump"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"

echo "======================================================================"
echo "[AURA BACKUP] Starting database backup for '${POSTGRES_DB}'"
echo "  Timestamp: ${TIMESTAMP}"
echo "  Target:    ${BACKUP_FILE}"
echo "======================================================================"

# Execute pg_dump with custom compressed archive format (-Fc)
# -Fc allows parallel restore, compression, and fine-grained table selection
if command -v pg_dump >/dev/null 2>&1; then
    PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_dump \
        -h "${POSTGRES_HOST}" \
        -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" \
        -Fc \
        -b \
        -v \
        -f "${BACKUP_FILE}"
else
    # Fallback to docker exec if running via Docker container
    echo "[AURA BACKUP] pg_dump not on PATH; attempting via docker exec aura-postgres..."
    docker exec aura-postgres pg_dump \
        -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" \
        -Fc \
        -b > "${BACKUP_FILE}"
fi

# Verify backup was created and is non-empty
if [ ! -s "${BACKUP_FILE}" ]; then
    echo "ERROR: Backup file ${BACKUP_FILE} was not created or is empty!" >&2
    exit 1
fi

# Compute SHA256 checksum for tamper-evidence and integrity verification
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${BACKUP_FILE}" > "${CHECKSUM_FILE}"
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${BACKUP_FILE}" > "${CHECKSUM_FILE}"
fi

FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[AURA BACKUP] Backup created successfully (${FILE_SIZE}): ${BACKUP_FILE}"

# Rotate backups older than RETENTION_DAYS
echo "[AURA BACKUP] Purging backups older than ${RETENTION_DAYS} days in ${BACKUP_DIR}..."
find "${BACKUP_DIR}" -type f \( -name "*.dump" -o -name "*.dump.sha256" \) -mtime "+${RETENTION_DAYS}" -exec rm -f {} +

echo "[AURA BACKUP] Backup process completed successfully."
