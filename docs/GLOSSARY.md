# AURA Engineering Glossary

Plain-English definitions of technical terms used throughout the AURA architecture and codebase.

---

### Agentic AI
An AI system that does not merely generate passive text, but autonomously formulates plans, interacts with its environment via tools, observes outcomes, and loops until a goal is achieved.

### RAG (Retrieval-Augmented Generation)
A technique where external knowledge (documents, notes, memories) is retrieved from a search index or vector database and injected into the language model's prompt as grounded reference material before it generates an answer.

### Provenance
The documented origin, history, and derivation of a piece of data. In AURA's memory system, provenance records exactly which conversation, message, or document gave birth to a stored memory.

### pgvector
An open-source extension for the PostgreSQL relational database that allows storing vector embeddings and performing fast vector similarity searches (such as cosine distance) directly alongside traditional relational tables.

### Argon2id
A modern, award-winning password hashing algorithm designed to resist brute-force attacks powered by both specialized hardware (ASICs/GPUs) and memory-hard attacks. It is recommended by OWASP for password security.

### Policy Engine
A trusted backend software component that evaluates proposed actions against security rules and permissions before any tool execution occurs, returning `ALLOW`, `REQUIRE_APPROVAL`, or `DENY`.

### Confused Deputy Problem
A security vulnerability where an authorized entity (like AURA's backend) is tricked by an untrusted source (like malicious instructions hidden inside a user document) into misusing its authority to perform unauthorized actions.

### Idempotency
A property of an operation whereby performing it multiple times produces the exact same outcome as performing it once. Essential for durable automation and network retries so users aren't charged or emailed twice.

### Model Context Protocol (MCP)
An open standard proposed by Anthropic that allows AI applications to connect with external data sources and tools through standardized clients and servers.

### ADR (Architecture Decision Record)
A lightweight document capturing an important architectural decision made on a software project, along with its context, considered alternatives, and consequences.
