---
name: inbound-webhooks
description: Set up real inbound webhook endpoints that external services (GitHub, CI, any HTTP client) can trigger -- not a form that writes to a list nothing reads.
trigger_keywords:
  - inbound webhook
  - incoming webhook
  - trigger from github
  - webhook endpoint
  - external trigger
  - receive a webhook
---

Nancy has real inbound webhook endpoints (`inbound_webhooks_store.py` +
`POST /webhooks/inbound/{id}`) -- an external service can POST to a real URL
and it genuinely triggers one of the same four real actions cron jobs use:
`telegram_message`, `agent_task`, `run_skill`, `terminal_command`.

- Create one: `POST /webhooks/inbound` with `{"name", "action_type",
  "action_payload"}`. The response includes a real HMAC-SHA256 `secret` --
  this is shown ONLY once, at creation; store it, since later reads only
  show `has_secret: true`.
- The external caller must sign requests: `X-Nancy-Signature: sha256=<hex>`
  computed as HMAC-SHA256 of the raw request body using the shared secret
  (the exact same scheme GitHub/Stripe webhooks use). A missing or wrong
  signature is rejected with 401 -- never tell the user a hook is "secure"
  if they created it without a secret.
- List/manage: `GET /webhooks/inbound`, `PATCH /webhooks/inbound/{id}?enabled=`,
  `DELETE /webhooks/inbound/{id}`.
- For `run_skill`, the external request's real JSON body is appended to the
  skill's context automatically -- the external caller can't choose which
  skill or command runs (that's fixed at setup), only that a specific
  pre-configured hook fires.

## Answering

- After creating a hook, give the user the real URL
  (`<backend base>/webhooks/inbound/<id>`) and the one-time secret, and
  explain the signature header their external service needs to send.
- If asked "what webhooks do I have," answer from `GET /webhooks/inbound`'s
  real trigger_count/last_result, not a guess.
