# Messaging integration contract (SMS, WhatsApp, email)

**Status:** foundation implemented and tested (R1 WP5, M3) with the `none` and `synthetic` providers only.
**No messaging provider is connected and no message has ever been sent.** Production refuses any provider except
`none`.

## What exists

| Piece | Where |
|---|---|
| Consent to be contacted (append-only, per subject, channel and address, with purposes, wording version and how it was given) | `contact_consents`; `POST/GET /farmers/{id}/contact-consents`, `/buyers/{id}/contact-consents`; suppliers page panel |
| Templates, versioned in code (reviewable in git; each message records the key and version) | `src/backend/app/notifications/application/templates.py` |
| Notifications from outbox events: one per event, template and recipient (idempotent) | `notifications/application/service.py`, called by the worker in a savepoint |
| Delivery status and history | `notifications`, `notification_status_events`; `GET /notifications`, `GET /notifications/{id}`; Notifications page |
| Provider interface | `notifications/application/providers.py`: `send(OutboundMessage) -> ProviderResult` |
| Configuration | `NOTIFICATION_PROVIDER=none` (default) or `synthetic`; anything else is refused at startup |
| Migration | `0028_notifications_consent` (row-level security on Supabase) |

## Rules (tested in `tests/test_wp5.py`)

1. **Consent:**
   - Nothing is queued without a current GRANTED consent covering the template's purpose. Without one, the
     notification is recorded as `BLOCKED_NO_CONSENT` and shown.
   - Consent is re-checked just before sending, so a withdrawal stops queued messages.
   - The address is read from the current consent at send time. It is never stored on the notification, never put
     in domain events, and always masked in API responses.
2. **Event sources:**
   - Only these outbox events create messages:
     - supplier request, reminder and reply-date change (`solicitation.*`);
     - release agreement recorded (`supplier.release_agreed`);
     - delivery recorded, to the buyer (`delivery.recorded`).
   - Events written by the recovery agent itself (`actor_type = agent`) never produce a message. An agent draft
     reaches a supplier only after the existing human approval, as the gateway's execution.
3. **Failures and retries:**
   - A failed send retries with backoff (60 s doubling), up to 5 attempts, then becomes `FAILED`.
   - Every status change is kept.
   - A notification defect cannot undo or retry the supply-exception and recovery handling of the same event.
4. **What `none` and `synthetic` do:**
   - With `none`, queued messages become `NOT_SENT_PROVIDER_DISABLED`.
   - `synthetic` records in memory and reports `SENT`; addresses ending `-fail` fail, to exercise retries.

## Statuses

`QUEUED` → `SENT` (→ `DELIVERED` once a provider reports it) | `FAILED` | `BLOCKED_NO_CONSENT` | `NOT_SENT_PROVIDER_DISABLED`

## Product-owner decisions (5 November 2026)

**Channel priorities** (provisional; not authorization to choose a provider or connect anything):

| Audience | First channel | Alternative |
|---|---|---|
| Farmers and suppliers | WhatsApp | SMS |
| Institutional buyers | Email | none |

**Rules:**
- `NOTIFICATION_PROVIDER=none` outside synthetic testing.
- Staging must not message real phone numbers or email addresses.
- Consent wording is versioned: `MESSAGING_CONSENT_WORDING.md` (`supplier-whatsapp-sms-v1-draft`,
  `buyer-email-v1-draft`). Each version names the sender, channel, purposes and how to withdraw.
- Consent to receive messages is never acceptance of a supply commitment.

## Connecting a real provider later (product-owner decisions first)

**Decisions:**
1. Which channel or channels, and which provider.
2. The consent wording, its version label, and how consent is collected (signed form, recorded call, in the portal).
3. A data-processing review of the provider: where messages and numbers are stored, how long they are kept, and
   whether they are used for training.
4. Cost limits and the sending window.
5. Whether staging may send to real numbers. **Recommended: test numbers only.**

**Engineering:**
- Add a provider class with the same `send` signature, with a provider status callback endpoint that writes
  `DELIVERED` or `FAILED` to the status history.
- Add an allow-list for the provider host.
- Keep credentials in server environment files only (`deploy/.env`), as with the model providers.

Nothing is sent from production until separately authorized. That restriction stays in code
(`core/config.py`), not only in policy.

## Template wording (draft for review)

**Templates:**
- `SUPPLIER_REQUEST`
- `SUPPLIER_REMINDER`
- `SUPPLIER_DEADLINE_CHANGED`
- `RELEASE_AGREEMENT_RECORDED`
- `BUYER_DELIVERY_RECORDED`

**Wording rules:**
- each message says nothing is agreed until the supplier accepts;
- "no answer" is never taken as yes or no.

Changing wording means a new template version, never an edit of an existing one.
