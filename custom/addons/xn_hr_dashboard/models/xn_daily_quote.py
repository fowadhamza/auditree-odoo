# -*- coding: utf-8 -*-
"""The daily inspiration quote shown on the dashboard.

One quote, the same for every employee, changing at midnight.

The selection is a pure function of the date and the number of active
quotes:

    index = (today - 1970-01-01).days % count

Three properties follow from that, and all three are the reason it is not
done any other way:

* **Everyone sees the same quote on the same day.** A random pick differs
  per user and, worse, per page refresh - people compare screens and read
  that as a broken dashboard.
* **It rotates with nothing running.** No cron writing a record each night,
  so there is no scheduled job to fail silently. This module writes nothing
  at all, which is a rule the rest of the dashboard already follows.
* **Adding a quote cannot corrupt the rotation.** It shifts which quote
  lands on which day and nothing else. There is no stored pointer to
  migrate.

``fields.Date.context_today`` is what puts the day boundary at midnight
where the reader is rather than midnight UTC.

ASCII only - see CLAUDE.md section 3.3. Quote text attracts curly
apostrophes and em dashes, and a Windows-side write has already destroyed
the Unicode in this repository once.
"""

from datetime import date

from odoo import api, fields, models

# Any fixed date works as the origin; the epoch is just the conventional one.
_EPOCH = date(1970, 1, 1)


class XnDailyQuote(models.Model):
    _name = "xn.daily.quote"
    _description = "Daily Inspiration Quote"
    _order = "sequence, id"

    text = fields.Text(
        string="Quote",
        required=True,
        help="Shown on the dashboard without surrounding quotation marks; "
             "the view adds those.",
    )
    author = fields.Char(
        string="Author",
        help="Left blank for proverbs and anything whose attribution does "
             "not survive checking.",
    )
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Archive a quote to take it out of the rotation without losing "
             "it. Archiving re-indexes the remaining quotes.",
    )

    @api.model
    def _xn_quote_of_the_day(self):
        """The quote for today, or False when there are none to show.

        False rather than a placeholder: the template renders nothing at all
        for it. An empty card teaches people to ignore that part of the
        screen, which is the one thing a quote panel cannot afford.

        The read is elevated because only HR managers hold read on this
        model. Every employee sees their quote line; nobody outside that
        group can reach the list itself, by menu, by URL or over RPC. This is
        the one place in the module where sudo is not paired with a manager
        check, and deliberately so: what it exposes is a single line of a
        public quotation, chosen by the calendar, with nothing in it that
        varies by who is asking.

        The day is computed on ``self`` and not on the elevated recordset.
        ``context_today`` falls back to ``env.user.tz``, and under sudo that
        user is the superuser, whose timezone is not the reader's - so
        elevating first would quietly move the midnight boundary.
        """
        today = fields.Date.context_today(self)

        quotes = self.sudo().search([])
        if not quotes:
            return False

        index = (today - _EPOCH).days % len(quotes)
        quote = quotes[index]
        return {
            "text": (quote.text or "").strip(),
            "author": (quote.author or "").strip(),
        }
