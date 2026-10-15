# AURA Preliminary Threat Model

Security in AURA is an architectural invariant, not a post-deployment checklist.

---

## 1. Assets to Protect
* User account credentials and active session tokens.
* Personal memory entries and private life data.
* Uploaded sensitive documents (resumes, financial statements, research).
* System compute resources and external service connections.
* Audit trail integrity.

---

## 2. Threat Scenarios & Mitigations

| Threat | Impact | Implemented / Planned Defense |
| :--- | :--- | :--- |
| **Direct Prompt Injection** | Attacker tries to bypass system instructions via chat prompt | System prompt hardening, strict tool schema validation, model has no direct execution privileges |
| **Indirect Prompt Injection** | Untrusted document or webpage contains hidden instructions to exfiltrate data | Retrieved RAG chunks tagged as untrusted data; Policy Engine blocks privileged tool execution without human sign-off |
| **Cross-Tenant Data Leakage (IDOR)** | User A queries or deletes User B's memories or documents | Server-side ownership filtering (`user_id == current_user.id`) enforced on all database queries and repository calls |
| **Memory Poisoning** | Malicious content repeatedly planted to manipulate future LLM reasoning | Memory provenance tracking, confidence metrics, and manual review/editing interfaces |
| **Confused Deputy Attack** | Agent runs high-risk operations on user's behalf without explicit awareness | Action-specific, expiration-bounded cryptographic approvals for mutating/external tools |
| **Secret Exfiltration** | Prompts or logs expose database passwords, API keys, or private tokens | Configuration strictly segregated from prompts; structured logs redact credentials; `.gitignore` guards `.env` |
| **Runaway Agent Loops** | Agent gets stuck in recursion consuming memory and compute | Hard upper bounds on tool calls per turn (e.g. max 5 steps), execution timeouts, and global pause kill switches |
