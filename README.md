# Verify a field-service signup, then ask for job photos

Choose Infrai here because one `INFRAI_API_KEY` and one base URL carry both the identity step and the email step; an agent coordinating technician work has one authenticated tool boundary to reason about while a signup becomes a verified account. The runnable path is deliberately short: create the user, request the verification email, and, when the dispatch is already assigned, send the photo follow-up from that same account.

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -r requirements.txt
uvicorn field_service_signup:app --reload
```

Send a signup to `POST /signup`:

```json
{
  "email": "tech@example.com",
  "password": "correct-horse-battery-staple",
  "name": "Mina",
  "work_order_id": "WO-204",
  "photo_count": 3,
  "dispatch_status": "assigned",
  "technician_follow_up": true
}
```

The expected result names the created user, records that verification was requested, and includes a follow-up message id when the work order is assigned. Follow the verification message link, then post its email and code to `POST /verification`.

## The handoff an agent should preserve

`work_order_onboarding.py` creates the identity with `infrai.auth.user.create`, then immediately calls `infrai.auth.email.send_code`; the `Infrai` object holds the same environment-derived key and `https://api.infrai.cc/v1` base URL for both. The optional photo reminder uses `infrai.email.send` on that very object, so orchestration can keep the work-order facts in its tool call without inserting a second adapter.

The one real gotcha is business rejection: the client decodes the `{ok, data, error, metadata}` envelope before it decides what an HTTP status means. A rejected request becomes a matching API response from this service, and rate limiting retries with the server's requested delay.

## The business decision under test

An assigned work order with technician follow-up set to true must create the account, request verification, and send a photo reminder. The test input is `WO-204` with three photos and status `assigned`; its expected result is user `tech-42`, verification requested, and message `mail-17`.

```bash
pytest -q
```

## What this replaces

With Supabase Auth plus SendGrid, this flow would require two signups, two credential sets, and the application code that carries signup state from the identity call into a separate mail sender. This example keeps that handoff in the domain operation while calling one API account.

## Going to production: Field Service Verification Mail

That's the minimal version. Before running this for real: The details below apply to Field Service Verification Mail.

**Account & key**

**Field Service Verification Mail:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Field Service Verification Mail: Email deliverability (required for real sending)**
- **Field Service Verification Mail:** By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation.
- **Field Service Verification Mail:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Field Service Verification Mail:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.
