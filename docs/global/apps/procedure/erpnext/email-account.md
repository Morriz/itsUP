---
description: Give one ERPNext site its own outgoing sender, overriding the bench-wide default.
---

# Configure An ERPNext Outgoing Email Account — Procedure

## Required reads

- @~/.teleclaude/docs/apps/spec/erpnext/person-roles.md

## Goal

One company sends business mail — invitations, password resets, invoices, correspondence —
from its own address instead of the sender the bench provides to every site.

## Preconditions

The company brings one of two things, and the choice decides everything downstream:

- **Control of its domain's DNS**, when the fleet relay sends on the company's behalf. The
  company publishes the relay's domain-verification, SPF, and DKIM records, and a
  return-path record when the relay asks for one. It keeps no mailbox credentials in the
  site, and its normal mail server continues to receive replies.
- **A mailbox it sends from**, when the company relays through its own provider: the address,
  the outgoing server, port, transport security, and credentials that authenticate. Providers
  that enforce multi-factor authentication require an application password or an explicitly
  enabled SMTP authentication path for that mailbox; the account password alone fails.

Both paths also require:

- The sender address and the display name recipients see, decided by the company's owner.
- A person at the company with authority over that address or that domain.
- The company's expected sending volume, checked against the provider's limits before
  invoices depend on it.
- The operator runs under the site's `System Manager` authority: its owner, or an agent in
  the site's administrator context. A company's agent operator identity lacks this authority
  and does not perform this procedure.
- The company's owner has decided the sender identity, which is a business decision about
  how the company appears to its customers.

## Steps

1. **Establish the sender identity with the owner.** Confirm the address mail is sent as and
   the display name recipients see. Both appear on every invoice and every invitation the
   company sends, so the owner decides them.
2. **Prepare the sending path the company chose.** For a company sending on its own domain
   through the fleet relay, publish the relay's verification, SPF, and DKIM records in that
   domain's DNS and confirm the provider reports the domain and sender as verified. For a
   company relaying through its own provider, collect the outgoing server, port, transport
   security, and the credential that authenticates — an application password where the
   provider enforces multi-factor authentication. Credentials travel through the approved
   secret channel, never through chat.
3. **Create the Email Account record** on that site with outgoing enabled and marked as the
   default outgoing account. Its presence is what overrides the bench-wide default, and its
   scope is that one site.
4. **Verify with a real message.** Send to an address the owner controls and confirm arrival,
   sender address, and display name. A saved record proves configuration, not delivery.
5. **Record the outcome** with the company's operating evidence: the sender identity, the
   server it relays through, and the date delivery was verified. The password stays in the
   account record and appears nowhere else.

## Outputs

- The site sends business mail as the company's own sender.
- A delivery verification the owner witnessed.

## Recovery

- **Mail is accepted but never arrives:** the transport authenticated and the recipient's
  domain rejected or filtered the message. Check the sender domain's SPF, DKIM, and DMARC
  alignment for the relay before changing anything on the site.
- **Authentication fails:** confirm the login the provider expects, which is often the full
  address rather than a local part, and whether the provider requires an application
  password instead of the account password.
- **The company reverts to the shared sender:** disable or remove the record; the site falls
  back to the bench-wide default.

## Discipline

Sender identity is how a company appears to its customers, so the owner decides it and an
agent executes it. Delivery is proven by a received message, never by a saved record. The
business CLI stays uninvolved: mail transport is site administration, not a business
operation, and the company's operator identity is deliberately powerless here.

## See Also

- ~/.teleclaude/docs/apps/procedure/erpnext/create-site.md
