# ADR-0001: Selection of Modular Monolith Architecture and Core Tech Stack

## Context
AURA is an agentic personal AI assistant requiring authenticated web sessions, relational persistence, vector search for memory and RAG, stateful agent orchestration, and durable automation. The system must be maintainable by a single engineer, testable locally, and deployable to affordable or free-tier hosting environments without high operational overhead.

## Decision
1. **Architecture Style:** We adopt a **modular monolith** backend (FastAPI) rather than a distributed microservices architecture. All core services (Auth, Memory, RAG, Policy Engine, Agent Harness) will share a single cohesive codebase with strictly enforced domain boundaries and explicit schemas.
2. **Backend Framework:** **Python with FastAPI and Pydantic v2** for asynchronous performance, native type safety, automated OpenAPI documentation, and rich integration with the AI/ML ecosystem.
3. **Database & Vector Store:** **PostgreSQL with pgvector**. PostgreSQL provides ACID-compliant relational integrity for users, sessions, and audit logs, while `pgvector` enables unified vector storage without the operational burden and cost of a separate vector database (e.g. Pinecone).
4. **Agent Orchestration:** **LangGraph** for explicit, stateful, directed acyclic and cyclic graphs, combined with a custom Python policy engine for security gating.
5. **Durable Automation:** **DBOS** as the planned durable execution layer for surviving interruptions and scheduling reliable jobs.

## Alternatives Considered
* *Microservices Architecture:* Rejected due to high deployment complexity, network latency, distributed transaction difficulties, and excessive resource overhead on modest hardware.
* *Separate Vector Database (Pinecone, Qdrant, Chroma):* Rejected to avoid maintaining multiple stateful databases and synchronization bugs between relational user data and vector embeddings.
* *Unconstrained Agent Frameworks (AutoGPT/CrewAI):* Rejected due to weak server-side permission controls and lack of deterministic verification mechanisms.

## Consequences
* **Positive:** Single deployment target, straightforward end-to-end testing, zero network hops between relational data and embeddings, clear debugging paths.
* **Negative:** If a specific subcomponent requires massive scaling later, it must be extracted into a separate service at that future stage.
