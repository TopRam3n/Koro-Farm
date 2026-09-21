# KoroFarm tenancy and authorization boundary

## Current boundary

KoroFarm currently authenticates a Supabase bearer token and then grants that
authenticated user access to the shared application dataset. Domain tables do
not yet carry an organisation or tenant identifier, and API queries are not
scoped by membership, role, buyer, programme, or fulfilment node.

This is acceptable only for the isolated synthetic demo environment. It is not
safe for multiple real customers or real farmer records.

## Production blocker

Real customer onboarding is blocked until the application has all of the
following:

- an `organisations` model and explicit ownership on every tenant-scoped row;
- user-to-organisation membership with least-privilege roles;
- server-side authorization policies for every read and mutation;
- PostgreSQL row-level security, or an equivalently enforced data-access layer,
  as defence in depth;
- object/evidence storage paths scoped and authorized by organisation;
- cross-tenant negative tests for list, detail, mutation, export, and indirect
  identifier access;
- an auditable service-role policy for background jobs and administrators;
- retention, deletion, consent, and incident-response rules for farmer data.

Supabase authentication establishes identity; it does not by itself establish
permission to a KoroFarm buyer, programme, farmer, requirement, or shipment.

## Demo rule

`ALLOW_INSECURE_DEMO_AUTH=true` remains permitted only when `APP_ENV` is `demo`
or `test`. Demo data must remain synthetic and must never share a database with
production records.
