from odoo import models, fields, api
from num2words import num2words


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # Salary categories that are totals or deductions rather than earnings.
    # Everything else on the slip counts as an earning, so an allowance sitting
    # in its own category (HRA, LTA, Special, ...) prints instead of being
    # silently dropped.
    NON_EARNING_CATEGORIES = ('DED', 'GROSS', 'NET')

    def _format_payslip_amount(self, amount):
        """Render an amount the way the printed payslip expects.

        Zero prints as a dash, matching the deduction column on the Auditree
        payslip format.
        """
        if not amount:
            return '-'
        return '{:,.2f}'.format(abs(amount))

    def get_total_working_days(self):
        """Total working days covered by the payslip period."""
        self.ensure_one()
        return sum(self.worked_days_line_ids.mapped('number_of_days'))

    def get_days_worked(self):
        """Days actually worked, i.e. the normal paid working-time line."""
        self.ensure_one()
        return sum(
            line.number_of_days
            for line in self.worked_days_line_ids
            if line.code == 'WORK100'
        )

    def get_lop_days(self):
        """Loss of pay days.

        Every worked-days line that is not normal working time is treated as
        unpaid. That holds while WORK100 is the only paid worked-days code in
        use -- if paid leave ever gets its own worked-days line it would be
        counted here too, and this needs a code-based rule instead.
        """
        self.ensure_one()
        return self.get_total_working_days() - self.get_days_worked()

    def get_gross_total(self):
        """Gross pay, as computed by the GROSS salary rule."""
        self.ensure_one()
        return sum(
            line.total for line in self.line_ids
            if line.category_id.code == 'GROSS'
        )

    def get_net_total(self):
        """Net pay, as computed by the NET salary rule."""
        self.ensure_one()
        return sum(
            line.total for line in self.line_ids
            if line.category_id.code == 'NET'
        )

    def get_deduction_total(self):
        """Total deductions, summed from the deduction lines themselves."""
        self.ensure_one()
        return sum(
            abs(line.total) for line in self.line_ids
            if line.category_id.code == 'DED'
        )

    def get_report_values(self):
        """Pair earnings and deductions side by side for the payslip PDF.

        Earnings are every line whose category is not a deduction or a total.
        The two columns are independent, so the table runs to whichever side
        has more lines and pads the other with blanks.
        """
        self.ensure_one()
        lines = self.line_ids.sorted(key=lambda line: line.sequence)
        earnings = lines.filtered(
            lambda line: line.category_id.code not in self.NON_EARNING_CATEGORIES
        )
        deductions = lines.filtered(
            lambda line: line.category_id.code == 'DED'
        )

        report_data = []
        for index in range(max(len(earnings), len(deductions))):
            earning = earnings[index] if index < len(earnings) else None
            deduction = deductions[index] if index < len(deductions) else None
            report_data.append({
                'earnings': earning.name if earning else '',
                'amount': self._format_payslip_amount(earning.total) if earning else '',
                'deductions': deduction.name if deduction else '',
                'deduction_amount': (
                    self._format_payslip_amount(deduction.total) if deduction else ''
                ),
            })
        return report_data

    # Number system used to spell out the net amount. 'en_IN' gives Indian
    # lakh/crore wording, which is what the Auditree payslip format uses.
    # Switch to 'en' for thousand/million wording.
    AMOUNT_WORDS_LANG = 'en_IN'

    def _number_to_words(self, number):
        """Spell a whole number in title case, without hyphens or commas."""
        text = num2words(int(abs(number)), lang=self.AMOUNT_WORDS_LANG)
        text = text.replace('-', ' ').replace(',', ' ')
        # num2words inserts "and" before the tens; the payslip format omits it.
        words = [w for w in text.split() if w != 'and']
        return ' '.join(words).title()

    def amount_to_words(self, net):
        """Spell the net amount the way the Auditree payslip format does.

        93000.0    -> 'Ninety Three Thousand Only'
        1500000.0  -> 'Fifteen Lakh Only'
        93500.5    -> 'Ninety Three Thousand Five Hundred and Fifty Paise Only'
        """
        net = net or 0.0
        whole = int(abs(net))
        paise = int(round((abs(net) - whole) * 100))
        words = self._number_to_words(whole)
        if paise:
            words = '%s and %s Paise' % (words, self._number_to_words(paise))
        if net < 0:
            words = 'Minus %s' % words
        return '%s Only' % words
