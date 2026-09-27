-- ============================================================================
-- OPERATOR CONTROL PLANE — Supabase Schema v2 (Part 1: Core & Enums)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "btree_gist";

CREATE TYPE lifecycle_state AS ENUM (
    'SEED', 'HATCHED', 'PROBATION', 'ACTIVE', 'DEGRADED', 
    'BLOCKED', 'QUARANTINED', 'SUSPENDED', 'UPGRADING', 'RETIRED', 'ARCHIVED'
);
CREATE TYPE priority_level AS ENUM ('P0', 'P1', 'P2', 'P3');
CREATE TYPE override_state AS ENUM ('ACTIVE', 'OVERRIDDEN', 'SUSPENDED');
CREATE TYPE verification_result AS ENUM ('PASS', 'FAIL', 'UNVERIFIED', 'REPAIR_REQUIRED');
CREATE TYPE mission_status AS ENUM ('QUEUED', 'ACTIVE', 'AWAITING_VERIFICATION', 'COMPLETED', 'FAILED', 'BLOCKED', 'SUPERSEDED');
CREATE TYPE delegation_status AS ENUM ('ACTIVE', 'REVOKED', 'QUARANTINED', 'EXPIRED');
CREATE TYPE open_loop_status AS ENUM ('PENDING', 'BLOCKED', 'IN_PROGRESS', 'AWAITING_INPUT');