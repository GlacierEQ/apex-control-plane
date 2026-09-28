-- Restore the intended service-role privilege boundary for federated execution permits.
-- Supabase default/table privileges can leave broader privileges than an additive GRANT implies.
-- These permit and receipt tables are consumed through bounded insert/select paths; service_role
-- must not retain UPDATE, DELETE, or TRUNCATE authority over append-only execution evidence.

revoke all on table public.continuity_federated_execution_permits_v1 from service_role;
revoke all on table public.continuity_federated_execution_permit_receipts_v1 from service_role;

grant select, insert on table public.continuity_federated_execution_permits_v1 to service_role;
grant select, insert on table public.continuity_federated_execution_permit_receipts_v1 to service_role;
