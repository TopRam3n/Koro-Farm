# KoroFarm ingestion API v1

## Boundary

External systems submit observations to a versioned ingestion boundary. An
adapter never writes around domain validation:

`external input -> adapter -> validation -> provenance -> domain command -> event`

Authenticated endpoints require a Supabase bearer token, an active membership,
`X-Organization-ID`, the applicable permission, and an `Idempotency-Key` for
commands. Correlation IDs, payload digests, validation outcomes, resulting
events, actor, channel, and timestamps are retained. Raw sensitive source
payloads are not retained by the general ingestion ledger.

## Implemented contracts

### Secure farmer actions

- `POST /v1/ingestion/secure-links` creates a time-limited, opaque,
  single-purpose token for an organization-scoped farmer and production lot.
- `GET /v1/secure-actions/{token}` returns only the minimum request context.
- `POST /v1/secure-actions/{token}` records the permitted response once.

Tokens are stored only as SHA-256 digests. Expired, revoked, reused, tampered,
or out-of-scope actions are rejected. A successful response is
`SELF_REPORTED`; existence does not make it verified.

### Coordinator-assisted observations

`POST /v1/ingestion/coordinator-observations` accepts production-lot updates
received by `PHONE`, `WHATSAPP`, or `COORDINATOR_ENTRY`. The record distinguishes
the coordinator who entered it from the farmer source. Values cannot reduce
availability below already reserved supply.

### CSV imports

- `GET /v1/ingestion/imports/templates/{farmers|production_lots|buyer_requirements}`
- `POST /v1/ingestion/imports/preview`
- `POST /v1/ingestion/imports/{import_id}/confirm`

Preview returns every rejected row, warning, and validation message. Confirm
imports only accepted rows and is idempotent. Re-uploading identical content
for the same entity and organization is rejected as a duplicate even if the
file name changes.

## Prepared future adapters

Buyer procurement, aggregator, warehouse, government/agriculture, and
logistics adapters should translate their payload into these commands. They
must not introduce channel-specific domain rules or claim connectivity before
credentials, delivery evidence, and integration tests exist.

## Messaging

`MessagingProvider` is provider-neutral. The repository currently implements
only `ConsoleMessagingProvider`, whose delivery state is
`LOGGED_NOT_DELIVERED`. WhatsApp, Twilio, and SMS are not connected. Future
messages should carry secure response links; the messaging provider is not the
system of record.
