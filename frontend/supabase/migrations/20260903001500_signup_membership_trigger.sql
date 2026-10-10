-- Provision the signup persona inside the trusted auth.users insert transaction.
-- The browser may request FARMER/BUYER in signup metadata, but cannot choose role/status:
-- this trigger validates persona and assigns the server-owned role/status values.
create or replace function public.handle_korofarm_signup()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare requested_persona text := upper(coalesce(new.raw_user_meta_data ->> 'signup_persona', ''));
begin
  if requested_persona in ('FARMER', 'BUYER') then
    insert into public.app_memberships(user_id, organization_id, persona, role, status)
    values (
      new.id,
      'individual-' || new.id::text,
      requested_persona,
      case when requested_persona = 'FARMER' then 'PRODUCER' else 'MEMBER' end,
      'ACTIVE'
    )
    on conflict (user_id, organization_id, persona) do nothing;
  end if;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created_korofarm_membership on auth.users;
create trigger on_auth_user_created_korofarm_membership
  after insert on auth.users
  for each row execute procedure public.handle_korofarm_signup();
