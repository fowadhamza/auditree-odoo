# Odoo Features from the KRA Register

**Source:** `KRAs - Master Combined_V10 - rebalanced workload.xlsx`, Master KRA Register sheet
**Prepared:** 28 October 2026

## Summary

The KRA register lists 554 recurring support tasks totalling about **7,770 hours a year**. Most of the hours fall on four people:

| Person | Annual hours |
|---|---|
| Ayesha | ~1,560 |
| Junaid | ~1,490 |
| Danyal | ~1,360 |
| Nishath | ~1,160 |

A large share of that time goes into keeping trackers up to date, emailing other teams to ask for the next step, and following up until it is done, rather than into the task itself. Odoo can take over that tracking and chasing. Ten features follow, ranked by how many hours they save against the effort needed to build them.

| # | Feature | Hours/yr in scope | Effort | Depends on |
|---|---|---|---|---|
| 1 | Joiner and leaver checklists | ~120 | Low | -- |
| 2 | Asset lifecycle | ~630 | Medium | Purchase approval (live) |
| 3 | Compliance calendar | ~540 | Low to medium | -- |
| 4 | Licence and subscription renewals | ~80 | Low | Purchase approval (live) |
| 5 | Daily hiring update email | ~100 | Very low | Recruitment module (live) |
| 6 | Helpdesk for IT tickets and HR queries | ~140 | Low | IT Helpdesk module (built, not installed) |
| 7 | Leave and attendance feeding payroll | ~70 | Medium | -- |
| 8 | Client care in CRM | ~110 | Medium | -- |
| 9 | Training tracker | ~200 | Medium | -- |
| 10 | Bookkeeping in Odoo | ~350+ | High | Zoho Books to Odoo migration |

**How to read the hours.** "Hours in scope" is the total the register gives for the tasks a feature touches. Odoo removes the tracking, emailing and following up within those tasks, not necessarily the whole task, so actual savings will be lower. The register itself marks many of its estimates as "proposed - unvalidated".

**Recommended order:** 5, 1 and 6 first (about 360 hours in scope, little or no new code), then 3, then 2.

---

## 1. Joiner and leaver checklists

**Today.** When someone joins or leaves, HR emails IT for the mailbox and laptop, emails Admin for the asset dispatch, registers or deregisters the person with NASSCOM (NSR), and follows up on each request by email. IT and HR each keep separate exit checklists.

**In Odoo.** When HR creates an employee or starts an exit, Odoo automatically assigns a set of tasks, each with an owner and a due date:

| Owner | Joiner tasks | Leaver tasks |
|---|---|---|
| IT | Create Microsoft 365 and Odoo accounts, assign licence, set up laptop, test call | Revoke access, take back the asset, preserve the person's files |
| Admin | Dispatch the asset, collect the custody form | Track the courier, record the unboxing |
| HR | Send the appointment letter, register with NSR, induction, set up the call with the reporting manager | Exit checklist, update NSR status, full and final settlement inputs |

Each person sees their tasks in Odoo and gets reminders. HR sees at a glance what is still open.

**KRA tasks replaced:** H2R-028 to 032, H2R-036, H2R-050, H2R-089, IT-006, IT-025 to 028, IT-043, A2R-008 to 015, CMP-047 to 054

**Effort:** Low. Mostly configuring Odoo's built-in onboarding and offboarding plans.

---

## 2. Asset lifecycle

**Today.** Each asset passes through procurement, delivery, tagging, assignment, repair, surrender and the annual verification. Every step is tracked in Excel and ManageEngine, coordinated by email between IT, Admin and Accounts, and evidenced with unboxing videos shared by email.

**In Odoo.**
- An approved purchase order creates the asset record when the goods are received.
- The asset tag number is generated automatically, and the configuration and warranty are recorded on the asset.
- Assigning an asset to an employee sends them an acknowledgement to e-sign. The signed copy is stored on the asset.
- Repair status (*Under Repair*, spare device issued, returned) is tracked on the asset and linked to the helpdesk ticket.
- Surrender on exit closes the custody and returns the asset to *In Stock*.
- In the annual verification, each employee confirms the assets they hold, and Odoo lists any mismatches.
- Warranty expiry alerts.
- Unboxing videos are attached to the asset, not emailed.

**KRA tasks replaced:** the tracking, emailing and follow-up in A2R (procurement, movement, repair, surrender, unavailable assets, audit). About 150 of the ~630 hours is real work that stays: device configuration and security checks, quotation comparison, and payment approval and release.

**Effort:** Medium. Builds on the existing asset register (`xn_asset_register`) and the new purchase approval module.

### Gaps in the register

The 62 A2R tasks cover procurement in detail but leave gaps at the end of an asset's life and between IT and Accounts. These should be fixed in the register before the Odoo workflow is built, so Odoo doesn't copy them.

**Steps with no task today.** New KRA rows are needed for each:

| Step | What is missing |
|---|---|
| Lost or stolen device | Remote wipe or lock through Intune, a security incident record, a police report, an insurance claim. A2R-060 only identifies the loss, and FC-018 renews asset insurance but nothing claims on it. |
| Scrapping a device | Handing the device to an e-waste vendor, a data destruction certificate, removing it from Intune and ManageEngine, and recording any sale proceeds. A2R-061 approves the write-off and A2R-062 changes the status, but nobody carries it out. |
| Repair return | Receiving the repaired device, checking it, recovering the spare issued under A2R-056 and closing the ticket. Also missing: protecting the data before a device goes to an external repairer, checking the warranty before paying for a repair, and processing the repair bill. |
| Transfers and upgrades | Moving a device between existing staff, or replacing an old one. Assignment today only covers new joiners (A2R-020). |

**Decisions taken (29 October 2026):**
- **Ayesha owns the fixed-asset register.** R2R-008 and R2R-026 move from Junaid to Ayesha. Junaid keeps the operational device tracker. As written, IT kept both records and then reconciled them in A2R-005.
- **"Admin" is Mohammed Junaid P**, a different person from Junaid in IT. Mohammed Junaid P is missing from the Team & Profiles sheet and needs to be added with capacity hours. The role executes 16 A2R tasks (about 129 hours a year): delivery receipt, unboxing, stickering and courier follow-up. To avoid confusion with Junaid (IT), the register should use the full name rather than "Admin".

**Other fixes in the register:**
- A2R-022's executor still says Admin, though its action note says it moved to Junaid in V10. A2R-019 and A2R-029 also name a different executor from the one in their control text.
- A2R-034's control says Fowad approves larger purchases, but the reviewer column says Sharook.
- Some controls have no task or hours behind them: the monthly reconciliation of ManageEngine against the Asset Master (A2R-047), the monthly check of the procurement folder against the fixed-asset register (A2R-051) and the independent sample checks (A2R-001). A2R-018's monthly review "by IT lead" is Junaid reviewing his own work.
- No task passes asset additions (A2R-051) or write-offs (A2R-062) to the fixed-asset register (R2R-026), and no task passes damage or unreturned assets to the final settlement (H2R-105).
- The annual audit only collects employee self-declarations (A2R-003, A2R-004). It needs a physical count of spare stock and of devices away for repair.
- Occurrence counts disagree: the joiner tasks assume 12 a year, but A2R-021, A2R-022 and A2R-026 assume 24, and the logistics bills (A2R-023) assume 60. A2R-011, a surrender task, is triggered by "Procurement or asset request raised".
- Junaid executes 405 of the 631 A2R hours and is at 99% utilisation. 40 A2R rows list Ayesha, at 104%, as backup. No backup has been tested.

**In Odoo** this adds *Lost*, *Disposed* and *At vendor* statuses, a repair-return step that recovers the spare, a disposal step that requires the certificate, a transfer action between employees, and a stock count in the annual verification. Disposals and additions post to the asset books (`om_account_asset`) for Ayesha's review.

---

## 3. Compliance calendar

**Today.** GST, TDS, PF, ESIC, PT, advance tax, the tax audit and annual licence renewals are tracked by memory and email, split between Ayesha, Nishath and the outsourced partner. The register flags the control check as "thin" for most of these.

**In Odoo.** A Compliance project with one recurring task per obligation. Each task has:
- the statutory due date and an internal target date, for example "support documents 15 days before filing"
- the person who does it and the person who reviews it
- the proof (challan, filed return) uploaded on the task
- automatic reminders before the due date, and escalation to the reviewer and partner when it is overdue

One screen shows what is due this month, what is late, and what has been filed with proof. That covers the "Proof of execution" and "Control check" columns of the register.

**KRA tasks replaced:** CMP-001 to 061 (tracking and evidence; the filing work itself stays the same)

**Effort:** Low to medium. Recurring tasks in Odoo's Project app plus an overdue-escalation rule.

---

## 4. Licence and subscription renewals

**Today.** Licence counts, renewal dates and subscription reminders live in ManageEngine and Excel trackers. Renewals are requested and approved by email.

**In Odoo.**
- A renewal register with the vendor, licence count, cost and renewal date.
- An alert to IT and Accounts 30 days and 7 days before renewal.
- The renewal goes through purchase approval automatically.
- The monthly bill for recurring subscriptions (for example, 33 Microsoft 365 licences) is created automatically each month at the current licence count.

**KRA tasks replaced:** IT-039 to 042, IT-005, FC-014, P2P-013, P2P-014

**Effort:** Low. Extends the purchase approval module (`xn_purchase_approval`).

---

## 5. Daily hiring update email

**Today.** HR updates the hiring tracker every day and shares it with the partners. That one task, H2R-021, is budgeted at **100 hours a year**.

**In Odoo.** The recruitment module already has a hiring-status report. A scheduled job emails it to the partners every morning, with open roles, candidates by stage and yesterday's movements. Nobody maintains a separate tracker.

**KRA tasks replaced:** H2R-021

**Effort:** Very low. One scheduled job on a module that is already live.

---

## 6. Helpdesk for IT tickets and HR queries

**Today.** IT requests and employee queries arrive by email and chat. Deadlines (24 to 48 hours for software issues, 24 hours for HR queries) are tracked by hand.

**In Odoo.**
- Install the IT Helpdesk module (`xn_it_helpdesk`), which is already built.
- Add an HR team for employee queries and ordinary grievances. (The independent whistleblower channel stays outside Odoo.)
- Each team has a response deadline, with reminders for overdue tickets.

**KRA tasks replaced:** IT-004, IT-029 to 032, H2R-051, H2R-052, H2R-078, H2R-079

**Effort:** Low. The module exists; the HR team is configuration.

---

## 7. Leave and attendance feeding payroll

**Today.** Each month HR extracts timesheets, compiles loss-of-pay days, comp-off payouts, deductions and reimbursements, and emails them to Accounts for payroll.

**In Odoo.** Approved leave, comp-off and timesheet hours flow straight into the payslip as inputs, with no extraction. Accounts reviews the inputs on the payslip batch instead of in an email.

**KRA tasks replaced:** H2R-061 to 064, H2R-083, H2R-084, H2R-096 to 098, part of H2R-099 and H2R-101

**Effort:** Medium. Links the existing leave, timesheet and payroll modules.

---

## 8. Client care in CRM

**Today.** Catch-up meetings, client satisfaction (CSAT) forms, quarterly business reviews, contract renewals and client due diligence (KYC) are scheduled and tracked by Nishath through email and files on the drive.

**In Odoo.**
- CSAT forms sent and scored through Odoo Surveys, with results on the client record.
- Recurring reminders for catch-ups and quarterly business reviews per client, with minutes and action items logged on the client.
- Contract and statement-of-work renewal dates, with alerts.
- A client due-diligence (KYC) and acceptance checklist before an engagement starts.

**KRA tasks replaced:** CRM-003, CRM-005, CRM-009 to 012, CRM-017 to 020, CRM-023, CRM-027, CRM-028, CRM-032, CRM-033

**Effort:** Medium.

---

## 9. Training tracker

**Today.** The training plan, invitations, trainer confirmations, attendance, reminders to people who missed sessions, and the skill matrix are all handled by email and Excel.

**In Odoo.**
- The annual training plan as scheduled sessions.
- Invitations with calendar entries.
- Attendance and feedback recorded on each session.
- Automatic reminders to anyone who missed a mandatory training.
- Completion and certificates stored on the employee record, ready as ISO 27001 evidence.

**KRA tasks replaced:** TRN-001 to 030, H2R-034, H2R-088, IT-021 to 023, ASR-008

**Effort:** Medium.

---

## 10. Bookkeeping in Odoo

**Today.** Books are kept outside Odoo. Manual journal entries, bank reconciliation, reconciling the debtor, creditor and fixed-asset sub-ledgers to the general ledger, and receivables aging take up much of Ayesha's time.

**In Odoo.** If the books move to Odoo:
- Bank statements are imported and matched against invoices and bills.
- The sub-ledger reconciliations disappear, because the sub-ledgers and the general ledger are the same records.
- Receivables aging and client payment follow-ups are built in.
- Vendor bills from purchase approval post straight to the books.

**KRA tasks replaced:** R2R-001, R2R-012 to 015, R2R-022, O2C-008, O2C-009, FC-002, FC-010

**Effort:** High. Depends on the decision about moving the accounts from Zoho Books to Odoo, which is still under discussion.

---

## Notes on the workbook

- Several columns on the *Sizing Working* sheet show `#REF!` errors where the earlier V8 figures used to be. The current estimates aren't affected, but the comparison columns need fixing.
- The hours in this document come from the register's *Est. annual hours* column as it stands in V10.
