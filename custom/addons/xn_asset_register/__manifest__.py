# -*- coding: utf-8 -*-
{
    "name": "Auditree Asset Register",
    "summary": "Asset codes and physical condition on maintenance equipment, "
               "so the IT asset register lives in Odoo instead of a spreadsheet.",
    "description": """
Tracks who holds which piece of company equipment, and what state it is in.

Why this sits on maintenance.equipment
--------------------------------------
The Auditree asset register is a custody list -- laptops, headphones, mice,
monitors, UPS units -- tracked by holder and condition, not a schedule of
depreciable assets. Core maintenance.equipment already carries almost every
column of the master sheet: category, model, serial number, purchase date
(effective_date), cost, location and notes. hr_maintenance adds employee_id
and equipment_assign_to, which is the 'Assigned to' column. It also gives
every employee an Equipment smart button for free.

om_account_asset was the wrong home for this. That module exists to post
depreciation journal entries, and a 309-rupee mouse has no business having a
depreciation board. The accounting side is a separate, later exercise; the two
are reconciled through the asset code, which is why that field is here.

What this module adds
---------------------
* Asset Code -- the AT-LT-002 style tag the master sheet is keyed on. Unique,
  indexed and searchable. Deliberately separate from Serial Number, which is
  the manufacturer's identifier, not ours.
* Condition -- Very Good / Good / Average / Bad / Not Working, matching the
  values already in use in the sheet.
* Assigned Date and Scrap Date, which core hides behind developer mode. A
  handover date is the point of a custody register, so it should not need
  developer mode to see.

Not included, pending a decision
--------------------------------
SIM cards (4 rows in the sheet, holding a phone number and provider) have no
home here yet. Whether they belong in Odoo at all is an open question, and
adding two fields that nothing fills is worse than leaving them out.
    """,
    "version": "17.0.1.0.0",
    "category": "Human Resources",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": [
        "hr_maintenance",
    ],
    "data": [
        "views/maintenance_equipment_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
