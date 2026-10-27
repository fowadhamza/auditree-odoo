# -*- coding: utf-8 -*-
{
    "name": "Auditree Purchase Approval",
    "summary": "Named approvers for purchase orders, approval from a link in "
               "an email, verified vendor bank accounts and pro-rata billing "
               "periods, so purchases stop running on email threads.",
    "description": """
Replaces the email chain IT -> Accounts -> approver -> Accounts that every
purchase used to go through.

Flow
----
1. Whoever raises the purchase (IT, Accounts, ...) creates a purchase order:
   vendor, products, quantities, the vendor's PI attached in the chatter, and
   optionally the employee it is for. Licence lines can carry a billing
   period and a monthly price; the pro-rata unit price is worked out from them.
2. Confirm Order picks the approver from Purchase > Configuration > Approval
   Rules (highest minimum amount the order reaches) and emails them a link.
3. The approver opens the link, sees the vendor, the bank account the money
   will go to, the lines and the attachments, and clicks Approve or Reject.
   The page works for any internal user -- the approver does not need
   Purchase access rights. Approving is a POST from that page, never the
   link itself, so mail scanners that pre-open links (Outlook Safe Links)
   cannot approve anything.
4. On approval a draft vendor bill is created with the PI attached and the
   vendor bank account filled in, ready for Accounts to post and pay.
   A rejection sends the order back to draft with the reason in the chatter.

Bank details
------------
An order cannot be confirmed for bank transfer unless the vendor has a bank
account marked Trusted ("Send Money", core field allow_out_payment). Only
users in "Validate bank account" can trust an account, and every change to an
account is tracked. Bank details pasted into an email are the classic
invoice-redirection fraud; this keeps them on the vendor record instead.

Orders paid by company card can tick "Paid by Card" to skip the check.

Not included
------------
Recurring monthly bills for subscriptions (e.g. 33 Microsoft 365 licences
every month) -- a separate step once this flow is in use.
    """,
    "version": "17.0.1.0.0",
    "category": "Inventory/Purchase",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": [
        "purchase",
        "account",
        "hr",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/mail_template_data.xml",
        "views/purchase_approval_rule_views.xml",
        "views/purchase_order_views.xml",
        "views/xn_purchase_review_templates.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
