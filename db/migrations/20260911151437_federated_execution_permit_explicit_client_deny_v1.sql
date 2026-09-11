-- Defense-in-depth RLS policies for internal federated execution permit state.
-- service_role access is controlled separately by table ACLs; anon/authenticated
-- clients are explicitly denied rather than relying on an empty-policy default.

drop policy if exists continuity_federated_execution_permits_client_deny_v1
  on public.continuity_federated_execution_permits_v1;
create policy continuity_federated_execution_permits_client_deny_v1
on public.continuity_federated_execution_permits_v1
for all
to anon, authenticated
using (false)
with check (false);

drop policy if exists continuity_federated_execution_permit_receipts_client_deny_v1
  on public.continuity_federated_execution_permit_receipts_v1;
create policy continuity_federated_execution_permit_receipts_client_deny_v1
on public.continuity_federated_execution_permit_receipts_v1
for all
to anon, authenticated
using (false)
with check (false);
