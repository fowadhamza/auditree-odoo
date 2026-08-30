# Switch Backend Theme: MuK → web_responsive

## Overview

Replace the current **MuK Backend Theme** suite (`muk_web_theme` + its 4 sub-modules) with the **OCA `web_responsive`** module already present on disk at `custom/addons/web_responsive/`.

`web_responsive` gives a cleaner, modern flat layout with two app-menu styles (**Milk** — light lavender, dark text; **Community** — brand-color gradient, white text), sticky list/form headers, fuzzy app search, and better mobile layout. It is production-stable (OCA), has no dependency on any currently installed custom module, and is already on disk — no sourcing required.

**Scope:** Odoo UI only. No business logic, data models, or reports are affected.

---

## Sub-Tasks

---

### Sub-Task 1 — Uninstall muk_web_theme (top of dependency chain)

**Intent**  
Uninstall `muk_web_theme` first. Its `uninstall_hook` (`_uninstall_cleanup`) resets all three color-asset SCSS bundles (light, dark, theme) back to Odoo defaults. This must run before the sub-modules are removed.

**Expected Outcomes**
- `muk_web_theme` state = `uninstalled` in `ir.module.module`
- Company `favicon` and `background_image` fields on `res.company` are dropped
- All `theme_color_*` settings fields removed from `res.config.settings`
- SCSS color assets reset to Odoo defaults
- UI falls back to bare Odoo (no styled theme)

**Todo List**
1. In Odoo backend → Settings → Apps, search for **MuK Backend Theme**
2. Click **Uninstall** and confirm
3. Odoo will automatically cascade-uninstall its dependents (`muk_web_chatter`, `muk_web_dialog`, `muk_web_appsbar`, `muk_web_colors`) in the correct order
4. Confirm all 5 modules show state = `uninstalled`

**Relevant Context**
- `custom/addons/muk_web_theme/__manifest__.py` — `uninstall_hook: _uninstall_cleanup`
- `custom/addons/muk_web_theme/models/` — removes `favicon`, `background_image` from `res.company`
- `custom/addons/muk_web_appsbar/models/res_users.py` — drops `sidebar_type` from `res.users`
- `custom/addons/muk_web_chatter/models/res_users.py` — drops `chatter_position` from `res.users`
- `custom/addons/muk_web_dialog/models/res_users.py` — drops `dialog_size` from `res.users`
- No other custom module depends on any `muk_web_*` module (verified)

**Status:** [x] done — verified via `ir_module_module`: all 5 (`muk_web_theme`, `muk_web_appsbar`, `muk_web_chatter`, `muk_web_colors`, `muk_web_dialog`) are `uninstalled`.

---

### Sub-Task 2 — Install web_responsive

**Intent**  
Install the OCA `web_responsive` module. It depends only on `web_tour` and `mail`, both of which are standard Odoo modules already active. No other preparation is needed.

**Expected Outcomes**
- `web_responsive` state = `installed`
- Three new fields added to `res.users`: `apps_menu_search_type`, `apps_menu_theme`, `is_redirect_home`
- New user preference panel visible in user settings (app menu theme + search type)
- UI is now served by `web_responsive`: sticky headers, flat layout, responsive control panel

**Todo List**
1. In Odoo backend → Settings → Apps, search for **Web Responsive**
2. Click **Install** and confirm
3. After install, open any list view and verify sticky header is working
4. Open Settings → Users → your user → Preferences and confirm the new **Apps Menu** preference section is visible

**Relevant Context**
- `custom/addons/web_responsive/__manifest__.py` — depends on `web_tour`, `mail`; excludes `web_enterprise`
- `custom/addons/web_responsive/models/res_users.py` — the 3 new fields
- `custom/addons/web_responsive/views/res_users_views.xml` — user preference UI

**Status:** [x] done — `web_responsive` was already in state `installed` in the database when this plan was executed; verified it stayed `installed` after the MuK uninstall. Restart the Odoo service to pick up the regenerated asset bundles.

---

### Sub-Task 3 — Configure the preferred app-menu theme

**Intent**  
Choose between the **Milk** (light lavender, clean) and **Community** (brand-color gradient, bold) app-menu styles. Set it as default for all users, or at minimum for the admin account.

**Expected Outcomes**
- App menu opens in the chosen theme style
- All users who have not set a preference inherit the chosen default

**Todo List**
1. Log in as admin → click the user avatar (top right) → **Preferences**
2. In the **Apps Menu** section, set **Theme** to either:
   - **Milk** — light lavender gradient, dark text (recommended for a professional/neutral look)
   - **Community** — brand-color gradient, white text (more Odoo-branded)
3. Set **Search Type** to **Fuse** for fuzzy search (much better UX) or **Canonical** for exact match
4. Save — confirm the app menu visually reflects the chosen theme
5. Optionally repeat for other user accounts or adjust the field default in `res_users.py` if a system-wide default is needed

**Relevant Context**
- `custom/addons/web_responsive/models/res_users.py` — `apps_menu_theme` default is `'milk'`
- `custom/addons/web_responsive/static/src/components/apps_menu/apps_menu.scss` — Milk: `rgb(233, 230, 249)` lavender; Community: `$o-brand-primary` gradient
- `custom/addons/web_responsive/static/src/components/apps_menu_item/apps_menu_item.scss` — text colors per theme

**Status:** [x] done — checked `res_users` table for all 42 users: every user already has `apps_menu_theme = 'milk'` and `apps_menu_search_type = 'canonical'` (field defaults), matching the chosen Milk theme. No per-user changes needed.

---

### Sub-Task 4 — Optional: Adjust brand colors to match Auditree identity

**Intent**  
`web_responsive` uses `$o-brand-primary` for the Community app-menu gradient and accent colors throughout the UI. If the default Odoo purple/blue doesn't suit the Auditree brand, update the primary color variable in a small SCSS override inside `xn_auditree_erp` (the existing custom module) — keeping all overrides in one place.

This sub-task is optional and only needed if the default colors feel off after Step 3.

**Expected Outcomes**
- `$o-brand-primary` overridden to a chosen Auditree brand color
- Accent buttons, active states, and Community app-menu gradient reflect the new color
- No new module created — override lives inside `xn_auditree_erp`

**Todo List**
1. Decide on a brand color for Auditree (hex value)
2. Create `custom/addons/xn_auditree_erp/static/src/scss/brand.scss` with the override:
   ```scss
   $o-brand-primary: #YOUR_COLOR;
   $o-brand-odoo: #YOUR_DARK_COLOR;
   ```
3. Register it in `xn_auditree_erp/__manifest__.py` under `web._assets_primary_variables` (inject `after` the base primary variables file)
4. Restart Odoo server and verify the color change

**Relevant Context**
- `custom/addons/xn_auditree_erp/__manifest__.py` — existing manifest to add the asset entry
- `custom/addons/web_responsive/static/src/legacy/scss/primary_variable.scss` — where `$app-menu-background-color` is set (references `$o-brand-primary`)

**Status:** [ ] skipped — optional, not requested

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| MuK uninstall breaks UI temporarily | Certain (brief) | Low | Expected — UI goes to Odoo default then web_responsive takes over |
| User chatter/sidebar preferences lost | Certain | Low | These are UI prefs, not business data — users simply reset in Preferences |
| Another module secretly depending on muk_web_* | None found | High | Verified: zero custom modules reference any muk_web_* module |
| web_responsive JS conflict with existing modules | Unlikely | Medium | web_responsive is OCA production-stable for 17.0; no conflicts found |

## Files Involved

- `custom/addons/muk_web_theme/` — uninstalled
- `custom/addons/muk_web_appsbar/` — uninstalled (cascade)
- `custom/addons/muk_web_chatter/` — uninstalled (cascade)
- `custom/addons/muk_web_colors/` — uninstalled (cascade)
- `custom/addons/muk_web_dialog/` — uninstalled (cascade)
- `custom/addons/web_responsive/` — installed
- `custom/addons/xn_auditree_erp/__manifest__.py` — modified (Sub-Task 4 only, optional)
- `custom/addons/xn_auditree_erp/static/src/scss/brand.scss` — created (Sub-Task 4 only, optional)
