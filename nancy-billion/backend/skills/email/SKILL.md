---
name: email
description: Send and read real email via a configured SMTP/IMAP account (send_email, list_recent_emails) -- not available unless EMAIL_ADDRESS/EMAIL_PASSWORD are set.
trigger_keywords:
  - send an email
  - compose an email
  - check my email
  - check my inbox
  - unread emails
  - list my emails
---

Nancy has two real email tools (`email_tools.py`), plain SMTP/IMAP -- no
vendor SDK, works with Gmail (via an app password, not the account
password), Outlook, or any standard mail provider.

- `send_email(to, subject, body)` -- **requires the user's explicit
  yes/no approval** before it sends, same tier as `send_sms`/
  `place_phone_call`. Never claim an email was sent if the approval was
  denied or the tool returned an error.
- `list_recent_emails(limit, unread_only)` -- read-only, no approval
  needed, real subject/sender/date for each real message in the inbox.

If neither tool is configured (`EMAIL_ADDRESS`/`EMAIL_PASSWORD` unset),
they return a real, honest error -- say plainly that email isn't set up
rather than pretending to send or check anything.
