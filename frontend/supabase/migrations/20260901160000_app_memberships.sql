create table if not exists public.app_memberships (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  organization_id text not null,
  persona text not null check (persona in ('BUYER','FARMER','OPS')),
  role text not null check (role in ('MEMBER','PRODUCER','ADMIN','COORDINATOR')),
  status text not null default 'PENDING' check (status in ('ACTIVE','PENDING','SUSPENDED')),
  created_at timestamptz not null default now(),
  unique(user_id, organization_id, persona)
);

alter table public.app_memberships enable row level security;
create policy "memberships_read_own" on public.app_memberships for select to authenticated using (user_id = auth.uid());
-- No client INSERT/UPDATE/DELETE policy is intentional: persona, role and status cannot be self-elevated.

create or replace function public.provision_signup_membership(requested_persona text)
returns void language plpgsql security definer set search_path = public as $$
declare uid uuid := auth.uid();
begin
  if uid is null then raise exception 'AUTH_REQUIRED'; end if;
  if requested_persona not in ('FARMER','BUYER') then raise exception 'INVALID_SIGNUP_PERSONA'; end if;
  insert into public.app_memberships(user_id, organization_id, persona, role, status)
  values (uid, 'individual-' || uid::text, requested_persona, case when requested_persona='FARMER' then 'PRODUCER' else 'MEMBER' end, 'ACTIVE')
  on conflict (user_id, organization_id, persona) do nothing;
end; $$;
revoke all on function public.provision_signup_membership(text) from public;
grant execute on function public.provision_signup_membership(text) to authenticated;
