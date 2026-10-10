-- Backfill accounts created before the signup-membership trigger existed.
-- Only accounts carrying an explicit FARMER/BUYER signup_persona are eligible.
insert into public.app_memberships(user_id, organization_id, persona, role, status)
select
  u.id,
  'individual-' || u.id::text,
  upper(u.raw_user_meta_data ->> 'signup_persona'),
  case when upper(u.raw_user_meta_data ->> 'signup_persona') = 'FARMER' then 'PRODUCER' else 'MEMBER' end,
  'ACTIVE'
from auth.users u
where upper(coalesce(u.raw_user_meta_data ->> 'signup_persona', '')) in ('FARMER', 'BUYER')
on conflict (user_id, organization_id, persona) do nothing;
