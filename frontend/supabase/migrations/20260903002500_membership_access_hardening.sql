-- RLS policies do not themselves grant table privileges. Make the own-membership
-- SELECT available to authenticated clients, while retaining write denial.
grant select on table public.app_memberships to authenticated;
revoke insert, update, delete, truncate, references, trigger on table public.app_memberships from anon, authenticated;

-- Do not hide membership provisioning failures from application diagnostics.
-- This function only reports whether the caller owns a membership; it cannot mutate access.
create or replace function public.has_app_membership()
returns boolean
language sql
stable
security invoker
set search_path = public
as $$
  select exists(select 1 from public.app_memberships where user_id = auth.uid());
$$;

revoke all on function public.has_app_membership() from public;
grant execute on function public.has_app_membership() to authenticated;
