# Joiner and Leaver Checklist: Team Answers

Answers to the email "Joiner & leaver checklist in Odoo" (sent 28 Oct 2026 to Danyal, Junaid K,
Mohammed Junaid P and Ayesha, cc Nishath). Feeds feature 1 in
[odoo-features-from-kra-register.md](odoo-features-from-kra-register.md).

| Person | Area | Status |
|---|---|---|
| Danyal | HR | Received |
| Junaid K / Mohammed Junaid P | IT | Pending |
| Ayesha | Accounts | Pending |

---

## HR (Danyal)

### Joining, in order

Each step waits on the previous one, so tasks need dependencies, not just date offsets.

1. Send rejection emails to unselected candidates. Negotiate the offer and finalise the date of
   joining (DOJ) with the selected candidate.
2. Finalise the offer with Management and email it with the Personal Information Form, BGV form,
   Bank Details form and the document list.
3. Candidate accepts within 3 business days and sends documents within 3-7 working days.
4. After the signed offer and consent arrive, start BGV (identity, education, employment, address,
   criminal). Review interim and final reports; discrepancies go to Management.
5. On a green BGV report plus all documents: send the Engagement Letter, Employee Handbook and
   Bond Agreement (if applicable) for signature; collect the signed scans.
6. Send the DOJ confirmation to the candidate.
7. Internal email with name, designation, department, DOJ and reporting manager:
   - Reporting manager: New Joinee Information.
   - IT: helpdesk ticket for asset handover and company ID creation.
8. Email the joiner (IT in copy) to sign and return the Asset Handover Form and Asset Declaration
   Form; follow up until both are received.
9. Induction, after the assets are delivered.
10. Track mandatory compliance: cyber security training, NSR registration, ISO training.

Steps 1-6 happen while the person is still an applicant, so they belong with recruitment
(`xn_recruitment`), not on an employee checklist. Step 7's IT request can create a ticket in
`xn_it_helpdesk`.

### Leaving, in order

1. Offboarding starts on the resignation or termination notice.
2. Reporting manager and HR Head jointly fix the last working day (LWD); HR emails it to the
   employee.
3. Employee completes knowledge transfer and handover before the LWD.
4. Exit interview at least 3 days before the LWD.
5. Initial Release Letter issued in the first half of the LWD.
6. On the LWD: reporting manager confirms handover is complete; HR emails IT to disable all access
   at close of office hours.
7. IT gives the employee the return address. The employee couriers the assets and shares the
   tracking ID and invoice (courier cost reimbursed by Auditree). IT and Admin inspect and email HR
   the status.
8. After IT confirms all assets are recovered and inspected, HR starts the Exit Checklist. Order:
   reporting manager, Admin, IT, Accounts, HR, then final review by the Operations Manager.
9. Full and final settlement with Accounts (pending dues, reimbursements, incentives, recoveries).
10. Relieving Letter and F&F Statement issued after settlement.

### Types of people

No differences. Consultants, interns, remote staff and client-specific hires all work on an
Auditree laptop under the same policy.

### Notice

- Joining: email from the hiring manager after selection. Needs at least 15 days (10 working
  days).
- Leaving: resignation email from the employee, or termination email from the manager or
  partners. Notice is usually 1 month (probation or contract) or 2 months (permanent). Rare
  immediate terminations on partner instruction.

### Dependencies

HR waits on:
- Onboarding: Management (offer approval); candidate (acceptance, documents, signed offer and
  consent, Engagement Letter, Bond, asset forms); IT (asset handover and ID creation, before
  induction can finish and the person can start work).
- Offboarding: reporting manager (handover complete, before access is cut); IT (asset recovery,
  before the Exit Checklist); Exit Checklist approvers in sequence (to fix the F&F date and
  amount).

Others wait on HR:
- Onboarding: candidate (DOJ confirmation); IT (helpdesk ticket for assets and ID).
- Offboarding: IT (instruction to disable access); Accounts (month-end attendance, and F&F after
  the Exit Checklist).

### Proof and where it is kept

- Email threads.
- Signed scans on the HR drive and SharePoint; hard copies filed at the office.
- Hiring Tracker (Excel, HR drive) for recruitment.
- Odoo for attendance and timesheets.

### What goes wrong

- Candidates late with documents or offer acceptance.
- BGV reports late (previous employers slow to confirm).
- Signed asset forms late or missing.
- Asset delivery delays, which hold up induction.
- Slow sequential approvals on the Exit Checklist.

### Wanted from Odoo

"Dunning": reminders on every missed or delayed timeline, across all processes.

### Differences from the KRA register

| Topic | KRA register | Danyal |
|---|---|---|
| Exit checklist | By the last working day | Starts after the LWD, once assets are recovered |
| Asset return form | By the last working day | Assets couriered after the LWD |
| Induction | On the joining date | After assets are delivered |
| Access cutoff | At the agreed cutoff | Close of office hours on the LWD |

### Follow-up questions for Danyal

- Who are the HR Head and the Operations Manager?
- How many days does each Exit Checklist approver get?
- What happens on an amber or red BGV, or if BGV is not back by the DOJ?
- When does the Bond Agreement apply?
- Is the Initial Release Letter a separate document from the Relieving Letter?
- How often should reminders repeat, and when should they escalate to Nishath?
