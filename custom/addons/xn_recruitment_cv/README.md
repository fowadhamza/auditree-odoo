# xn_recruitment_cv -- fill applications from the CV

Recruitment phase 2, item 1 (docs/HANDOFF.md section 3): HR's biggest
frustration was retyping each candidate's details from the CV.

## What it does

* **Read CV** button on the application (Recruitment Officers and up). Picks
  the attached PDF / .docx / .txt -- one named "CV" or "Resume" first, else
  the newest -- extracts the text, asks the AI for the facts as JSON and
  fills the **empty** fields. Safe to press again: it never overwrites.
* **Scheduled job** "Recruitment: read new CVs", every 15 minutes: any
  application with a file attached in the last 2 days that has not been read
  yet. It does not care how the CV arrived (job email alias, website form,
  chatter upload). Up to 20 per run.
* Chatter note on each read: which fields were filled, and where the CV
  disagrees with the application on name / email / phone. Those are left
  for HR.
* Job portal emails: when the application's email is an automated sender
  (`noreply`, `notification`, `alert`, `mailer` ...), its name and email count
  as empty and are replaced from the CV, and the application moves to a
  contact for the candidate. The portal's own contact is not changed.
* **CV Summary** tab: a few lines for the interviewers (education, work,
  skills; no salary or personal attributes). Re-reading replaces it.
* Search filter **CV Not Read**: no file, scanned CV, or the AI failed.

Fields filled: name, email, phone, LinkedIn, location, current employer,
current designation, qualification, CA / ACCA papers, CA Final attempts,
articleship completed, total and relevant experience, notice period, current
and expected CTC (only when the CV states them).

## Limits

* Scanned CVs (images) have no text layer: marked "No readable text".
* Old Word `.doc` files are not read; ask for PDF or .docx.
* PDF text comes from PyPDF2 1.26 on production, which sometimes runs words
  together; the model copes. If `pdfminer.six` is ever added to the venv it
  is used automatically and reads better.

## Privacy and cost

All calls go through `xn_ai_core` (purpose `recruitment_cv`): kill switch,
monthly token budget, request log. PAN / Aadhaar numbers in the CV are masked
before sending. Prompts and replies are not stored unless payload logging is
switched on in xn_ai_core. One CV is roughly 3-8k input tokens.

## Testing on a copy of production

The scheduled job runs only when AI is enabled (`xn_ai.enabled = True`). It
posts chatter notes (internal, no email) and makes AI calls -- nothing else
leaves the database.
