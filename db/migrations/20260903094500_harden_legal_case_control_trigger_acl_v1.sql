-- Harden internal legal-case trigger function privileges.
-- Applied as a new migration rather than rewriting the already-deployed
-- continuous-control-plane migration.

revoke all on function public.legal_case_control_immutable_v1()
  from public,anon,authenticated;

grant execute on function public.legal_case_control_immutable_v1()
  to service_role;

comment on function public.legal_case_control_immutable_v1() is
  'Internal service-role trigger function that enforces append-only legal case event/receipt history.';
