-- Decouple signup intent from auth.users metadata/trigger timing. The browser can request
-- FARMER/BUYER, but this RPC alone grants no application access. A second authenticated
-- RPC consumes the one-time intent and assigns server-controlled role/status.
create table if not exists public.signup_intents (
  email text primary key,
  persona text not null check (persona in ('FARMER','BUYER')),
  created_at timestamptz not null default now()
);

alter table public.signup_intents enable row level security;
revoke all on table public.signup_intents from anon, authenticated;

create or replace function public.register_signup_intent(requested_email text, requested_persona text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if upper(requested_persona) not in ('FARMER','BUYER') then raise exception 'INVALID_SIGNUP_PERSONA'; end if;
  if requested_email is null or position('@' in requested_email) = 0 then raise exception 'INVALID_EMAIL'; end if;
  insert into public.signup_intents(email, persona)
  values (lower(trim(requested_email)), upper(requested_persona))
  on conflict (email) do update set persona = excluded.persona, created_at = now();
end; $$;

create or replace function public.claim_signup_membership()
returns void language plpgsql security definer set search_path = public as $$
declare
  uid uuid := auth.uid();
  user_email text;
  requested_persona text;
begin
  if uid is null then raise exception 'AUTH_REQUIRED'; end if;
  select lower(email) into user_email from auth.users where id = uid;
  delete from public.signup_intents where email = user_email
    returning persona into requested_persona;
  if requested_persona is null then raise exception 'SIGNUP_INTENT_NOT_FOUND'; end if;
  insert into public.app_memberships(user_id, organization_id, persona, role, status)
  values (uid, 'individual-' || uid::text, requested_persona,
    case when requested_persona='FARMER' then 'PRODUCER' else 'MEMBER' end, 'ACTIVE')
  on conflict (user_id, organization_id, persona) do nothing;
end; $$;

revoke all on function public.register_signup_intent(text,text) from public;
revoke all on function public.claim_signup_membership() from public;
grant execute on function public.register_signup_intent(text,text) to anon, authenticated;
grant execute on function public.claim_signup_membership() to authenticated;
