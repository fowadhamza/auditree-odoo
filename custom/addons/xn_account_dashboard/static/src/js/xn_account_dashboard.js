/** @odoo-module **/
/**
 * Accounts Overview.
 *
 * One server call (xn.account.dashboard.xn_data) per load. Every width,
 * height and formatted amount is computed here, never in the template, so
 * what is drawn and what is counted cannot drift apart. No chart library:
 * bars are CSS boxes sized from these numbers.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

function percent(value, max) {
    if (!max || max <= 0) {
        return 0;
    }
    return Math.max(0, Math.min(100, (Math.abs(value) / max) * 100));
}

function readableDate(value) {
    if (!value) {
        return "";
    }
    const parsed = new Date(`${value}T00:00:00`);
    if (Number.isNaN(parsed.getTime())) {
        return String(value);
    }
    return parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export class XnAccountDashboard extends Component {
    static template = "xn_account_dashboard.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({ loading: true, error: false, data: null });
        onWillStart(() => this.load());
    }

    async load() {
        try {
            const raw = await this.orm.call("xn.account.dashboard", "xn_data", []);
            this.state.data = this.shape(raw);
        } catch (error) {
            console.warn("xn_account_dashboard: xn_data failed", error);
            this.state.error = true;
        }
        this.state.loading = false;
    }

    async refresh() {
        this.state.loading = true;
        await this.load();
    }

    // ------------------------------------------------------------------
    // Shaping
    // ------------------------------------------------------------------

    /**
     * Whole rupees with Indian grouping (12,34,567) when the company
     * currency is INR; the reader's own grouping otherwise.
     */
    money(value, currency) {
        const locale = currency.name === "INR" ? "en-IN" : undefined;
        const text = Math.round(Math.abs(value)).toLocaleString(locale);
        const sign = value < -0.5 ? "-" : "";
        // The sign leads the symbol: -Rs 4,000, not Rs -4,000.
        return currency.position === "after"
            ? `${sign}${text} ${currency.symbol}`
            : `${sign}${currency.symbol}${text}`;
    }

    shapeOpen(block, currency) {
        const max = Math.max(1, ...block.buckets.map((b) => Math.abs(b.value)));
        const topMax = Math.max(1, ...block.top.map((t) => Math.abs(t.value)));
        return {
            total: this.money(block.total, currency),
            overdue: this.money(block.overdue, currency),
            hasOverdue: block.overdue > 0.5,
            count: block.count,
            empty: block.count === 0,
            buckets: block.buckets.map((b, index) => ({
                label: b.label,
                value: this.money(b.value, currency),
                width: Math.round(percent(b.value, max) * 10) / 10,
                late: index > 0,
                zero: Math.abs(b.value) < 0.5,
            })),
            top: block.top.map((t) => ({
                name: t.name,
                value: this.money(t.value, currency),
                width: Math.round(percent(t.value, topMax) * 10) / 10,
            })),
        };
    }

    shape(raw) {
        const cur = raw.currency;
        const pnl = raw.pnl;
        const pnlMax = Math.max(1, ...pnl.months.flatMap((m) => [Math.abs(m.income), Math.abs(m.expense)]));
        const bankTotal = raw.cash.reduce((sum, row) => sum + row.balance, 0);
        const att = raw.attention;

        return {
            fyLabel: raw.fy_label,
            fyRange: `${readableDate(raw.fy_from)} to ${readableDate(raw.fy_to)}`,
            today: readableDate(raw.today),
            headline: [
                {
                    key: false,
                    label: "Cash in bank and cash",
                    value: this.money(bankTotal, cur),
                    note: `${raw.cash.length} account${raw.cash.length === 1 ? "" : "s"}, per the books`,
                },
                {
                    key: "receivable",
                    label: "To collect from customers",
                    value: this.money(raw.receivable.total, cur),
                    note: raw.receivable.overdue > 0.5
                        ? `${this.money(raw.receivable.overdue, cur)} overdue`
                        : "Nothing overdue",
                    warn: raw.receivable.overdue > 0.5,
                },
                {
                    key: "payable",
                    label: "To pay to vendors",
                    value: this.money(raw.payable.total, cur),
                    note: raw.payable.overdue > 0.5
                        ? `${this.money(raw.payable.overdue, cur)} overdue`
                        : "Nothing overdue",
                    warn: raw.payable.overdue > 0.5,
                },
                {
                    key: "income_fy",
                    label: `Profit, ${raw.fy_label} to date`,
                    value: this.money(pnl.profit_fy, cur),
                    note: `Income ${this.money(pnl.income_fy, cur)} less expenses ${this.money(pnl.expense_fy, cur)}`,
                    loss: pnl.profit_fy < -0.5,
                },
            ],
            attention: [
                {
                    key: "bank_unmatched",
                    show: att.bank_unmatched > 0,
                    value: String(att.bank_unmatched),
                    label: "bank lines not yet matched",
                    note: `${this.money(att.bank_unmatched_amount, cur)} net`,
                },
                {
                    key: "receivable_overdue",
                    show: att.receivable_overdue > 0.5,
                    value: this.money(att.receivable_overdue, cur),
                    label: "overdue from customers",
                    note: "by due date, or entry date where none is set",
                },
                {
                    key: "payable_overdue",
                    show: att.payable_overdue > 0.5,
                    value: this.money(att.payable_overdue, cur),
                    label: "overdue to vendors",
                    note: "by due date, or entry date where none is set",
                },
                {
                    key: "draft_entries",
                    show: att.draft_entries > 0,
                    value: String(att.draft_entries),
                    label: `draft entr${att.draft_entries === 1 ? "y" : "ies"}`,
                    note: "not in any figure on this page until posted",
                },
            ].filter((row) => row.show),
            receivable: this.shapeOpen(raw.receivable, cur),
            payable: this.shapeOpen(raw.payable, cur),
            pnl: {
                empty: pnl.months.every((m) => Math.abs(m.income) < 0.5 && Math.abs(m.expense) < 0.5),
                month: {
                    income: this.money(pnl.income_month, cur),
                    expense: this.money(pnl.expense_month, cur),
                    profit: this.money(pnl.profit_month, cur),
                    loss: pnl.profit_month < -0.5,
                },
                months: pnl.months.map((m) => ({
                    key: m.key,
                    label: m.label,
                    future: m.future,
                    current: m.current,
                    incomeHeight: Math.round(percent(m.income, pnlMax) * 10) / 10,
                    expenseHeight: Math.round(percent(m.expense, pnlMax) * 10) / 10,
                    title: `${m.label}: income ${this.money(m.income, cur)}, expenses ${this.money(m.expense, cur)}, profit ${this.money(m.profit, cur)}`,
                })),
            },
            cash: raw.cash.map((row) => ({
                id: row.id,
                name: row.name,
                type: row.type === "bank" ? "Bank" : "Cash",
                balance: this.money(row.balance, cur),
                unmatched: row.unmatched,
                lastDate: row.last_date ? readableDate(row.last_date) : "No transactions",
            })),
        };
    }

    // ------------------------------------------------------------------
    // Actions
    // ------------------------------------------------------------------

    async open(key) {
        if (!key) {
            return;
        }
        const action = await this.orm.call("xn.account.dashboard", "xn_open", [key]);
        this.actionService.doAction(action);
    }

    async openJournal(journalId) {
        const action = await this.orm.call("xn.account.dashboard", "xn_open_journal", [journalId]);
        if (action) {
            this.actionService.doAction(action);
        }
    }
}

registry.category("actions").add("xn_account_dashboard", XnAccountDashboard);
