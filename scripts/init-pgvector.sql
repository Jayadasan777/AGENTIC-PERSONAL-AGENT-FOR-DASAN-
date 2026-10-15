-- ==============================================================================
-- AURA Database Initialization
-- Automatically executed on initial container creation
-- ==============================================================================

-- Enable the pgvector extension for high-dimensional vector search
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable uuid-ossp extension for UUID generation if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
