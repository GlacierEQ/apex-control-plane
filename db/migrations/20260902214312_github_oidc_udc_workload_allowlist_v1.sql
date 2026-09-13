with target as (
  select bootstrap_ref
  from public.apex_github_bootstrap_sessions
  where status='completed'
    and owner_login='GlacierEQ'
  order by installed_at desc nulls last, updated_at desc
  limit 1
)
update public.apex_github_bootstrap_sessions s
set expected_repositories = case
      when coalesce(s.expected_repositories,'[]'::jsonb) @> '["GlacierEQ/UDC"]'::jsonb
        then s.expected_repositories
      else coalesce(s.expected_repositories,'[]'::jsonb) || '["GlacierEQ/UDC"]'::jsonb
    end,
    verification_detail = coalesce(s.verification_detail,'{}'::jsonb)
      || jsonb_build_object(
           'udc_public_action_face_admission',
           jsonb_build_object(
             'repository','GlacierEQ/UDC',
             'permission_ceiling','contents:read',
             'wildcard',false,
             'action','udc-supabase-bridge-ci',
             'admission_receipt','79d49324-645e-401d-9137-95fb481ca38f'
           )
         ),
    updated_at=now()
from target t
where s.bootstrap_ref=t.bootstrap_ref;
