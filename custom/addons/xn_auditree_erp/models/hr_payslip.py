from datetime import datetime, time

from odoo import models, fields, api
from num2words import num2words


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # Salary categories that are totals or deductions rather than earnings.
    # Everything else on the slip counts as an earning, so an allowance sitting
    # in its own category (HRA, LTA, Special, ...) prints instead of being
    # silently dropped.
    NON_EARNING_CATEGORIES = ('DED', 'GROSS', 'NET')

    def _group_indian(self, amount):
        """Group digits the Indian way: 12,34,567.00 rather than 1,234,567.00.

        Applied here rather than through the res.lang grouping so the change
        stays confined to the payslip and does not restyle every number in
        the system.
        """
        whole, _, fraction = '{:.2f}'.format(abs(amount)).partition('.')
        if len(whole) > 3:
            head, tail = whole[:-3], whole[-3:]
            groups = []
            while len(head) > 2:
                groups.insert(0, head[-2:])
                head = head[:-2]
            if head:
                groups.insert(0, head)
            groups.append(tail)
            whole = ','.join(groups)
        return '%s.%s' % (whole, fraction)

    def _format_payslip_amount(self, amount):
        """Render an amount the way the printed payslip expects.

        Zero prints as a dash, matching the deduction column on the Auditree
        payslip format. Everything else uses Indian digit grouping so the
        figures agree with the lakh/crore wording on the Amount In Words row.
        """
        if not amount:
            return '-'
        return self._group_indian(amount)

    def get_employee_code(self):
        """Employee code as printed on the payslip.

        The code is kept in the employee's Badge ID (`barcode`, e.g. AT-0025).
        `identification_id` is unused in this database -- it is empty on every
        employee -- so it only serves as a fallback here.
        """
        self.ensure_one()
        employee = self.employee_id
        return employee.barcode or employee.identification_id or ''

    def get_total_working_days(self):
        """Days in the payslip period, counted as calendar days.

        The Auditree payslip treats a month as its full length -- March prints
        31, not the 21 working days the resource calendar holds -- and pays for
        that many days less any loss of pay.
        """
        self.ensure_one()
        return (self.date_to - self.date_from).days + 1

    def get_lop_days(self):
        """Loss of pay: approved unpaid leave falling inside the period.

        Read from the leave records rather than the worked-days lines. Those
        lines cannot be used: no leave type in this database sets a code, so
        `get_worked_day_lines` labels every leave line 'GLOBAL' regardless of
        whether the leave was paid. Subtracting worked days from the period
        length would be worse still, counting weekends and paid leave as loss
        of pay.

        A leave straddling a month boundary contributes all of its days to
        both slips. No unpaid leave type is currently active, so this has not
        come up; it needs clamping to the period if one is enabled.
        """
        self.ensure_one()
        leaves = self.env['hr.leave'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'validate'),
            ('holiday_status_id.unpaid', '=', True),
            ('date_from', '<=', datetime.combine(self.date_to, time.max)),
            ('date_to', '>=', datetime.combine(self.date_from, time.min)),
        ])
        return sum(leaves.mapped('number_of_days'))

    def get_days_worked(self):
        """Days paid for: the period length less any loss of pay."""
        self.ensure_one()
        return self.get_total_working_days() - self.get_lop_days()

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
