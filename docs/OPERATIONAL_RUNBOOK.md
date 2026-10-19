# AURA Operational Runbook & Incident Response Guide

This runbook documents operational procedures, incident response plans, and disaster recovery workflows for the AURA Personal Agent system.

---

## 1. Emergency Kill Switch Activation

### Trigger Criteria
- Agent enters recursive execution loop or exhibits non-deterministic tool spamming.
- Suspicion of prompt injection leading to attempted unauthorized resource access.
- Anomaly detection flags unusual outbound network traffic from tool execution.

### Procedure
1. **Via CLI / API Endpoint:**
   ```bash
   curl -X POST https://aura.internal/api/v1/system/kill-switch/trigger \
     -H "Authorization: Bearer <ADMIN_TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{"reason": "Anomalous tool loop detected", "triggered_by": "oncall-eng"}'
   ```
2. **Via Docker / Direct Container Halt:**
   ```bash
   # Immediately freeze container execution
   docker compose pause backend
   # Inspect active state
   docker compose logs --tail=100 backend
   ```
3. **Recovery & Reset:**
   - Investigate audit log: `GET /api/v1/audit?action=TOOL_INVOCATION&limit=50`.
   - Clear erroneous task queues in DBOS/Redis.
   - Deactivate kill switch with audit justification:
     ```bash
     curl -X POST https://aura.internal/api/v1/system/kill-switch/reset \
       -H "Authorization: Bearer <ADMIN_TOKEN>"
     ```

---

## 2. Compromised Companion Device Revocation

### Trigger Criteria
- User reports lost, stolen, or rooted Android companion device.
- Suspicious biometric signature or unexpected device fingerprint anomalies.

### Immediate Invalidation Steps
1. Revoke device session immediately:
   ```bash
   curl -X POST https://aura.internal/api/v1/devices/{device_id}/revoke \
     -H "Authorization: Bearer <USER_ACCESS_TOKEN>"
   ```
2. Invalidate pending approval actions:
   - System automatically cancels all outstanding approval tokens assigned to the revoked device.
3. Invalidate Push Notification Token:
   - Clears FCM/APNs registration tokens from database to halt sensitive payload delivery.

---

## 3. Secret & JWT Key Rotation Runbook

### Primary Secrets
- `JWT_SECRET_KEY`: Used for access and refresh token signing.
- `ENCRYPTION_KEY`: Used for AES-256 memory payload and credential storage.
- `DATABASE_URL`: PostgreSQL credentials.

### Zero-Downtime Rotation Procedure
1. **JWT Secret Rotation:**
   - Deploy secondary secret in `JWT_SECRET_KEY_FALLBACK` to accept existing tokens.
   - Set new secret as primary `JWT_SECRET_KEY` for newly issued tokens.
   - Retain fallback for 7 days (maximum refresh token lifespan), then deprecate.
2. **Database Credential Rotation:**
   - Update user credentials in PostgreSQL:
     ```sql
     ALTER USER aura_app WITH PASSWORD '<NEW_SECURE_PASSWORD>';
     ```
   - Update `.env` or cloud secret manager.
   - Perform graceful rolling restart of backend instances (`docker compose up -d --no-deps backend`).

---

## 4. Cross-Device Sync Conflict & Queue Recovery

### Symptoms
- Disconnected Android client unable to sync after network reconnection.
- High `conflicted_count` in sync responses.

### Resolution Steps
1. Inspect user sequence counter:
   ```sql
   SELECT MAX(server_seq) FROM sync_change_log WHERE user_id = '<USER_UUID>';
   ```
2. Client Queue Flush & Resync:
   - Client requests delta starting from `cursor=0` to rebuild local Room DB:
     ```bash
     GET /api/v1/sync/changes?cursor=0&limit=200
     ```
   - Last-Write-Wins (LWW) ensures server state is consistent based on Lamport timestamps.

---

## 5. PostgreSQL & pgvector Backup and Restore

### Automated Daily Snapshot
```bash
# Dump compressed PostgreSQL database with embeddings
docker exec -t aura-postgres pg_dump -U aura_user -d aura_db -Fc > /backups/aura_$(date +%Y%m%d_%H%M%S).dump
```

### Full Disaster Recovery Restore
```bash
# Drop corrupt/compromised database
docker exec -t aura-postgres dropdb -U aura_user aura_db
docker exec -t aura-postgres createdb -U aura_user aura_db

# Restore from snapshot
docker exec -i aura-postgres pg_restore -U aura_user -d aura_db /backups/aura_target.dump

# Verify pgvector indexes
docker exec -t aura-postgres psql -U aura_user -d aura_db -c "REINDEX TABLE document_chunks;"
```
