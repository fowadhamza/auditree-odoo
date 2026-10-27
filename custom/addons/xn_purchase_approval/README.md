# Auditree Purchase Approval (`xn_purchase_approval`)

Moves purchase requests off email. Before this, a purchase such as an extra
Microsoft 365 licence went IT -> Accounts -> approver -> Accounts by email,
with the vendor's bank details pasted into the thread.

## Flow

1. **Raise** -- the requester creates a purchase order: vendor, lines, the
   vendor's PI attached in the chatter, optionally *For Employee*.
2. **Confirm Order** -- checks the vendor bank account is trusted, picks the
   approver from *Purchase > Configuration > Approval Rules* and emails them a
   *Review and approve* link. The order sits in *To Approve*.
3. **Review** -- the link opens `/xn_purchase/review/<id>?token=...` after the
   Odoo login (Microsoft login works). The page shows vendor, bank account,
   lines, totals and attachments, with Approve and Reject buttons. A rejection
   needs a reason, sends the order back to draft and notifies the requester.
4. **Approved** -- a draft vendor bill is created with the PI attached and the
   vendor bank account set. Accounts posts it and pays.

## Approval rules

When an order is confirmed, the active rule with the highest *Minimum Amount*
that the order total (in company currency) reaches decides the approver. If
no rule matches, the standard Purchase approval settings apply.

Once a rule assigns an approver, **only that user** can approve the order --
not other Purchase Managers. The core *Approve Order* button is hidden on
those orders; the approver gets a *Review and Approve* button instead.

On install, one rule (any amount -> ghazala.nishath@auditree.com) is created
if no rules exist and that user exists.

## Vendor bank accounts

An order cannot be confirmed for bank transfer unless its *Vendor Bank
Account* is trusted (core `allow_out_payment`, shown as *Send Money* on the
bank account). Only users with *Validate bank account* (Accounting) can set
it, and changes to bank accounts are tracked in the chatter. Verify a new
account by phone before trusting it -- bank details sent by email are how
invoice-redirection fraud works.

Tick *Paid by Card* for purchases that are not paid by bank transfer.

## Pro-rata licence lines

Fill *Monthly Price*, *Period From* and *Period To* on a line and the unit
price becomes:

    monthly price x days billed / days in the billing month ending on Period To

27 Oct - 8 Nov 2026 is 13 days of the 9 Oct - 8 Nov month (31 days). The unit
price stays editable when the vendor's PI rounds differently. The period is
copied into the vendor bill line description.

## Setup checklist

- Approvers need an internal user; no Purchase rights are required.
- Services such as licences should have *Control Policy = On ordered
  quantities* (product form, Purchase tab), otherwise no draft bill is created
  on approval and the order gets a chatter note saying so.
- Accounts users who trust bank accounts need *Validate bank account*.
- Outgoing mail must work for the approval email to arrive.

## Security notes

- The review page reads the order with `sudo()` only after checking the
  logged-in user is the order's approver and the token matches; anyone else
  gets 404.
- Approve and Reject are POST requests with CSRF. Mail scanners such as
  Outlook Safe Links open every link in an email, so a GET must never change
  anything.
- The token is cleared when an order is rejected or reset to draft, so an old
  email link stops working.

## Not included yet

Recurring monthly bills for subscriptions (e.g. 33 licences every month).
