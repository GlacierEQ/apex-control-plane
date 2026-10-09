-- Supersede only the historical, mission-reducing Context Compiler role purpose.
-- Preserve the original migration and existing role/version/assignment lineage.
-- Deliberately guarded: do not overwrite subsequently customized or stronger definitions.
-- This updates the role-description projection only; it does not automatically
-- reissue active hashed role-version contracts or prove runtime policy enforcement.
update public.oa_roles_v1
set purpose = 'Compile the complete mission-preserving, authority-aware context and verified continuation package before execution; selective loading may reduce irrelevant work but must not shrink Operator objectives, omit consequential evidence or capabilities, or impose an arbitrary execution ceiling.',
    updated_at = now()
where role_key = 'OA.ROLE.CONTEXT_COMPILER'
  and purpose = 'Compile the smallest sufficient authority-aware context package before execution.';
