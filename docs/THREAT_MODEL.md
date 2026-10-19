# AURA Comprehensive Threat Model (STRIDE Framework)

Security in AURA is an architectural invariant, not a post-deployment checklist. This document specifies the threat landscape, trust boundaries, STRIDE classification, and verified mitigations across all system layers.

---

## 1. System Trust Boundaries & Architecture Diagram

```
[ Android Companion / Web Client ] (Untrusted Network Boundary)
              |  TLS 1.3 / JWT Bearer
              v
[ FastAPI API Gateway & Auth Guard ] (Trust Boundary: User Isolation)
              |
      +-------+-------+--------------------+
      |               |                    |
[ Policy Engine ] [ DBOS Workflows ] [ Sync Engine ]
      |               |                    |
[ LangGraph Agent ]   |                    |
      |               v                    v
[ Sandboxed Tools ] [ PostgreSQL + pgvector ] [ Local Whisper / Piper ]
```

---

## 2. Assets & Impact Classification

| Asset | Confidentiality | Integrity | Availability | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **User Identity & JWT Keys** | Critical | Critical | High | Compromise allows impersonation. |
| **Personal Memory Store** | Critical | High | Medium | Contains diary entries, user habits, private facts. |
| **RAG Embeddings & Documents** | Critical | High | Medium | May contain resumes, bank statements, personal notes. |
| **Companion Approval Channel** | High | Critical | High | Controls authorization for dangerous tool execution. |
| **Sync Change Log** | High | Critical | High | Append-only sequence tracking cross-device mutations. |
| **Audit Trails** | High | Critical | High | Tamper-evident record of all system decisions. |

---

## 3. STRIDE Threat Analysis & Defense-in-Depth Mitigations

### 3.1. Spoofing
- **Threat:** Attacker crafts forged JWT tokens or uses the `alg: none` vulnerability to impersonate another user.
- **Mitigation:** Strict JWT validation enforcing `HS256`, rejecting tokens lacking cryptographic signatures, and verifying user existence in the database.
- **Threat:** Attacker spoofs biometric approval from an unauthorized mobile device.
- **Mitigation:** Backend validates hardware-bound approval tokens with single-use consumption and 60-second expiration limits, rejecting foreign device IDs.

### 3.2. Tampering
- **Threat:** Client alters sequence IDs or timestamps during offline sync push to overwrite valid server changes.
- **Mitigation:** Monotonic server sequence assignment (`server_seq`) is assigned exclusively by the server; Last-Write-Wins (LWW) conflict engine compares ISO timestamps with UTC enforcement.
- **Threat:** Prompt injection alters system agent instructions.
- **Mitigation:** Dynamic prompt separation: system instructions, conversation history, and untrusted tool outputs are strictly demarcated; tool schemas are validated via Pydantic.

### 3.3. Repudiation
- **Threat:** User or compromised agent denies executing a high-risk system command or sensitive data deletion.
- **Mitigation:** Structured immutable audit logs (`audit_events` table) record caller user ID, IP address, exact tool arguments, exit codes, and timestamps.

### 3.4. Information Disclosure (IDOR & SSRF)
- **Threat (IDOR):** Attacker inspects another user's devices, memories, conversations, or sync changelog.
- **Mitigation:** Strict database query predicate `WHERE user_id == current_user.id` enforced across all repository operations (100% verified by automated penetration tests).
- **Threat (SSRF):** Agent instructed to scrape a URL targets internal cloud metadata (`169.254.169.254`) or loopback services (`127.0.0.1`).
- **Mitigation:** Egress filter strictly validates destination IP addresses, rejecting RFC1918 private subnets, loopback addresses, link-local metadata addresses, and non-HTTP/HTTPS schemes.

### 3.5. Denial of Service (DoS)
- **Threat:** Attacker floods audio synthesis endpoint with enormous texts or uploads 1GB files to STT.
- **Mitigation:** Text inputs bounded to 5,000 characters; STT uploads strictly capped at 25MB (`413 Content Too Large`); sync batches capped at 200 mutations.
- **Threat:** Agent enters infinite recursive loop consuming CPU and LLM tokens.
- **Mitigation:** Step counter max bound (5 steps per turn) and global `EmergencyKillSwitch` halting graphs mid-turn.

### 3.6. Elevation of Privilege
- **Threat:** Sandboxed tool execution attempts shell breakout (`rm -rf /`, `:(){ :|:& };:`).
- **Mitigation:** Regex prohibited pattern filter, execution timeouts, non-root container user, and isolation of OS execution tools behind mandatory human biometric sign-off.
