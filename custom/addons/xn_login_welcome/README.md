# xn_login_welcome

A short animated welcome, shown once after each login. It shows:

- the company logo inside a ring that draws itself
- "Good morning, <first name>"
- today's date
- a progress bar

It fades out after about 2.5 seconds. Clicking skips it.

## How "once per login" works

`models/ir_http.py` overrides `ir.http.session_info()`:

- The first web client load of a session gets `xn_show_welcome: true`, and the session is marked `xn_welcome_shown`.
- Login and logout both start from a session without that key.
- Reloads and new tabs reuse the session, so they skip the welcome.

The login page and its controllers are not touched, so the website, signup and TOTP 2FA flows are unaffected.

## Files

- `static/src/welcome/welcome.js`: OWL component in the `main_components` registry. It renders nothing unless the flag is set. It is also skipped when the browser asks for reduced motion.
- `welcome.xml`: the overlay markup.
- `welcome.scss`: all of the animation, CSS keyframes only.
  - The accent colour is `$o-brand-primary`.
  - `FADE_MS` in the JS must match the fade-out duration.

## Install / remove

This is a new module: install it with `-i xn_login_welcome`, then restart, because the assets are bundled.

To turn it off, uninstall the module. Nothing else depends on it.
