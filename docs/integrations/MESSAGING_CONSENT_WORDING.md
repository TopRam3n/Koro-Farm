# Consent wording for messages outside the app (draft, versioned)

**Status:** drafts for product-owner and legal review. No consent has been collected with them, and no message is
sent: `NOTIFICATION_PROVIDER=none` everywhere except synthetic testing.

**Rules for every version:**
- Each version has a label. That label is recorded with every consent (`contact_consents.wording_version`), so it is
  always known what a person agreed to.
- A version is never edited after use; changing the text means a new version.
- Consent to receive messages is never acceptance of a supply request, a commitment, a price or a delivery. Messages
  only tell people that something is waiting for them; agreements are recorded separately, as today.
- Withdrawing consent stops queued messages before they are sent, and never affects the person's orders or
  commitments.

**Channel priorities** (product-owner decision, 5 November 2026; provisional; no provider selected):

| Audience | First channel | Alternative |
|---|---|---|
| Farmers and suppliers | WhatsApp | SMS |
| Institutional buyers | Email | none |

**Staging:**
- Staging must never message real phone numbers or email addresses.
- Use synthetic test addresses only, for example numbers from a test range the provider documents, or addresses
  ending `@example.invalid`.

## `supplier-whatsapp-sms-v1-draft` (farmers and suppliers)

> **Messages from [Organisation name] about supply requests**
>
> [Organisation name] would like to send you messages by **[WhatsApp / SMS]** to **[number]** about:
> - requests to supply produce, and the date we need your answer by;
> - reminders about requests you have not answered yet;
> - changes to an answer date;
> - confirmation that we recorded your agreement to release produce from an order.
>
> These messages only tell you that something is waiting. **Agreeing to receive them does not mean you agree to
> supply anything.** You accept or decline each request yourself, in your KoroFarm portal or by telling your
> coordinator. If you do not answer, that is not taken as yes or no.
>
> **Stopping messages.** You can stop these messages at any time: tell your coordinator, or reply STOP where the
> channel allows it. Stopping messages does not change any order or agreement.
>
> **Your number.** It is used only to send these messages. [Data-handling statement once a provider is chosen:
> where messages are processed and how long they are kept.]
>
> ☐ I agree to receive these messages by [WhatsApp / SMS].
> Name · Date · How consent was given (signed form / recorded call / portal)

## `buyer-email-v1-draft` (institutional buyers)

> **Delivery notices from [Organisation name]**
>
> [Organisation name] would like to email **[address]** when a delivery to you is recorded, so you can confirm what
> you received in your KoroFarm account.
>
> These emails are notices only. **Agreeing to receive them does not confirm any delivery or quantity**: you confirm
> each delivery yourself in your account.
>
> **Stopping emails.** You can stop them at any time: tell your supplier coordinator, or use the unsubscribe link once
> provided. Stopping emails does not change any order or delivery record.
>
> ☐ I agree to receive delivery notices by email.
> Name · Organisation · Date · How consent was given

## Mapping to purposes in code

| Wording version | Purposes recorded (`contact_consents.purposes`) |
|---|---|
| `supplier-whatsapp-sms-v1-draft` | `SUPPLY_REQUESTS`, `RELEASE_AGREEMENTS` |
| `buyer-email-v1-draft` | `DELIVERY_UPDATES` |

Before real use:
1. Remove "-draft" from the label after approval.
2. Add the provider's data-handling statement.
3. Confirm the STOP and unsubscribe mechanics with the chosen provider.
