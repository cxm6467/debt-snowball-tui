"""Debt Snowball TUI Application."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
)

from debt_snowball.calculator import (
    Debt,
    SnowballResult,
    calculate_snowball,
    load_debts_from_csv,
    save_debts_to_csv,
)

# ── Styles ──────────────────────────────────────────────────────────────────

CSS = """
Screen {
    background: $surface;
}

#main-container {
    height: 1fr;
}

#left-panel {
    width: 1fr;
    min-width: 60;
    border-right: solid $accent;
    padding: 0 1;
}

#right-panel {
    width: 1fr;
    min-width: 50;
    padding: 0 1;
}

.section-title {
    text-style: bold;
    color: $accent;
    padding: 1 0 0 0;
    text-align: center;
}

.sub-title {
    text-style: bold;
    color: $text;
    padding: 1 0 0 0;
}

#debt-table {
    height: auto;
    max-height: 16;
    margin: 0 0 1 0;
}

#schedule-table {
    height: 1fr;
    margin: 0 0 1 0;
}

#payoff-table {
    height: auto;
    max-height: 14;
    margin: 0 0 1 0;
}

#summary-panel {
    height: auto;
    padding: 1;
    background: $boost;
    margin: 1 0;
    border: solid $accent;
}

#next-target-panel {
    height: auto;
    padding: 1;
    background: $boost;
    margin: 1 0;
    border: solid $success;
}

#extra-payment-container {
    height: auto;
    padding: 1 0;
    layout: horizontal;
}

#extra-label {
    width: auto;
    padding: 0 1 0 0;
}

#extra-input {
    width: 20;
}

#edit-help {
    height: auto;
    color: $text-muted;
    padding: 0 0 1 0;
    text-align: center;
}

.highlight-row {
    background: $success 20%;
}
"""


class DebtSnowballApp(App):
    """A TUI for calculating debt snowball payments."""

    TITLE = "Debt Snowball Calculator"
    CSS = CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("e", "edit_balance", "Edit Balance"),
        Binding("s", "save_csv", "Save CSV"),
        Binding("r", "recalculate", "Recalculate"),
    ]

    csv_path: str = ""
    debts: list[Debt] = []
    result: Optional[SnowballResult] = None
    extra_monthly: reactive[float] = reactive(0.0)

    def __init__(self, csv_path: str) -> None:
        super().__init__()
        self.csv_path = csv_path
        self.debts = load_debts_from_csv(csv_path)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            with VerticalScroll(id="left-panel"):
                yield Label("Debts (Snowball Order)", classes="section-title")
                yield Label(
                    "Press [bold]E[/bold] to edit a balance | "
                    "[bold]S[/bold] to save | "
                    "[bold]R[/bold] to recalculate",
                    id="edit-help",
                )
                yield DataTable(id="debt-table")
                with Container(id="extra-payment-container"):
                    yield Label("Extra Monthly $:", id="extra-label")
                    yield Input(
                        value="0.00",
                        placeholder="0.00",
                        id="extra-input",
                        type="number",
                    )
                yield Static(id="next-target-panel")
                yield Static(id="summary-panel")
            with VerticalScroll(id="right-panel"):
                yield Label("Payoff Timeline", classes="section-title")
                yield DataTable(id="payoff-table")
                yield Label("Monthly Schedule (First 12 Months)", classes="section-title")
                yield DataTable(id="schedule-table")
        yield Footer()

    def on_mount(self) -> None:
        self._setup_debt_table()
        self._setup_payoff_table()
        self._setup_schedule_table()
        self._run_calculation()

    def _setup_debt_table(self) -> None:
        table = self.query_one("#debt-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("#", "Name", "Balance", "APR", "Min Payment")

    def _setup_payoff_table(self) -> None:
        table = self.query_one("#payoff-table", DataTable)
        table.cursor_type = "none"
        table.zebra_stripes = True
        table.add_columns("#", "Debt", "Payoff Month", "Payoff Date", "Total Paid")

    def _setup_schedule_table(self) -> None:
        table = self.query_one("#schedule-table", DataTable)
        table.cursor_type = "none"
        table.zebra_stripes = True
        table.add_columns(
            "Month",
            "Date",
            "Debt",
            "Payment",
            "Interest",
            "Principal",
            "Remaining",
            "Target",
        )

    def _run_calculation(self) -> None:
        # Sort debts smallest balance first
        self.debts.sort(key=lambda d: d.current_balance)
        self.result = calculate_snowball(self.debts, extra_monthly=self.extra_monthly)
        self._refresh_debt_table()
        self._refresh_next_target()
        self._refresh_summary()
        self._refresh_payoff_table()
        self._refresh_schedule_table()

    def _refresh_debt_table(self) -> None:
        table = self.query_one("#debt-table", DataTable)
        table.clear()
        for i, d in enumerate(self.debts, 1):
            balance_str = f"${d.current_balance:,.2f}"
            if d.is_paid_off:
                balance_str = "[green]PAID OFF[/green]"
            table.add_row(
                str(i),
                d.name,
                balance_str,
                f"{d.apr:.2f}%",
                f"${d.minimum_payment:,.2f}",
                key=d.name,
            )

    def _refresh_next_target(self) -> None:
        panel = self.query_one("#next-target-panel", Static)
        if self.result is None or not self.result.debts:
            panel.update("[bold]No debts to pay![/bold]")
            return

        # Find the first non-paid-off debt (snowball target)
        target = None
        for d in self.debts:
            if not d.is_paid_off:
                target = d
                break

        if target is None:
            panel.update("[bold green]All debts are paid off![/bold green]")
            return

        # Calculate snowball payment for this target
        other_mins = sum(
            d.minimum_payment for d in self.debts if d.name != target.name and not d.is_paid_off
        )
        snowball_payment = self.result.monthly_budget - other_mins

        text = (
            f"[bold green]>>> NEXT SNOWBALL TARGET <<<[/bold green]\n\n"
            f"  [bold]{target.name}[/bold]\n"
            f"  Balance:         ${target.current_balance:,.2f}\n"
            f"  APR:             {target.apr:.2f}%\n"
            f"  Minimum Payment: ${target.minimum_payment:,.2f}\n"
            f"  [bold]Snowball Payment: ${snowball_payment:,.2f}[/bold]\n"
            f"    (${target.minimum_payment:,.2f} min + "
            f"${snowball_payment - target.minimum_payment:,.2f} extra)"
        )
        panel.update(text)

    def _refresh_summary(self) -> None:
        panel = self.query_one("#summary-panel", Static)
        if self.result is None:
            panel.update("")
            return

        r = self.result
        total_balance = sum(d.current_balance for d in self.debts)
        years = r.total_months // 12
        months = r.total_months % 12

        text = (
            f"[bold $accent]SUMMARY[/bold $accent]\n\n"
            f"  Total Debt:         ${total_balance:>12,.2f}\n"
            f"  Monthly Budget:     ${r.monthly_budget:>12,.2f}\n"
            f"  Extra Payment:      ${r.extra_payment:>12,.2f}\n"
            f"  Total Interest:     ${r.total_interest_paid:>12,.2f}\n"
            f"  Months to Payoff:   {r.total_months:>12}\n"
            f"  Time to Debt Free:  {years}y {months}m\n"
        )
        panel.update(text)

    def _refresh_payoff_table(self) -> None:
        table = self.query_one("#payoff-table", DataTable)
        table.clear()
        if self.result is None:
            return

        for i, event in enumerate(self.result.payoff_events, 1):
            table.add_row(
                str(i),
                event.name,
                f"Month {event.month_number}",
                event.date.strftime("%b %Y"),
                f"${event.total_paid:,.2f}",
            )

    def _refresh_schedule_table(self) -> None:
        table = self.query_one("#schedule-table", DataTable)
        table.clear()
        if self.result is None:
            return

        # Show first 12 months of detailed schedule
        for month_sched in self.result.schedule[:12]:
            for mp in sorted(month_sched.payments, key=lambda p: -p.payment_amount):
                if mp.payment_amount < 0.01:
                    continue
                target_marker = "[bold green]*[/bold green]" if mp.is_snowball_target else ""
                table.add_row(
                    str(month_sched.month_number),
                    month_sched.date.strftime("%b %Y"),
                    mp.debt_name,
                    f"${mp.payment_amount:,.2f}",
                    f"${mp.interest_charged:,.2f}",
                    f"${mp.principal_paid:,.2f}",
                    f"${mp.remaining_balance:,.2f}",
                    target_marker,
                )

    # ── Actions ─────────────────────────────────────────────────────────────

    def action_edit_balance(self) -> None:
        """Open input to edit the selected debt's balance."""
        table = self.query_one("#debt-table", DataTable)
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self.debts):
            debt = self.debts[table.cursor_row]
            self.push_screen(
                EditBalanceScreen(debt.name, debt.current_balance),
                callback=self._on_balance_edited,
            )

    def _on_balance_edited(self, result: tuple[str, float] | None) -> None:
        if result is None:
            return
        name, new_balance = result
        for d in self.debts:
            if d.name == name:
                d.current_balance = new_balance
                break
        self._run_calculation()

    def action_save_csv(self) -> None:
        """Save current debt balances back to CSV."""
        save_debts_to_csv(self.csv_path, self.debts)
        self.notify(f"Saved to {self.csv_path}", title="Saved")

    def action_recalculate(self) -> None:
        """Force recalculation."""
        self._run_calculation()
        self.notify("Recalculated!", title="Updated")

    @on(Input.Changed, "#extra-input")
    def on_extra_input_changed(self, event: Input.Changed) -> None:
        try:
            value = float(event.value)
            if value >= 0:
                self.extra_monthly = value
                self._run_calculation()
        except ValueError:
            pass


# ── Edit Balance Screen ─────────────────────────────────────────────────────


EDIT_CSS = """
EditBalanceScreen {
    align: center middle;
}

#edit-dialog {
    width: 50;
    height: 12;
    border: thick $accent;
    background: $surface;
    padding: 1 2;
}

#edit-title {
    text-align: center;
    text-style: bold;
    padding: 0 0 1 0;
}

#edit-input {
    margin: 1 0;
}

#edit-hint {
    text-align: center;
    color: $text-muted;
}
"""


class EditBalanceScreen(ModalScreen[tuple[str, float] | None]):
    """Modal screen for editing a debt balance."""

    CSS = EDIT_CSS

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, debt_name: str, current_balance: float) -> None:
        super().__init__()
        self.debt_name = debt_name
        self.current_balance = current_balance

    def compose(self) -> ComposeResult:
        with Vertical(id="edit-dialog"):
            yield Label(f"Edit Balance: [bold]{self.debt_name}[/bold]", id="edit-title")
            yield Input(
                value=f"{self.current_balance:.2f}",
                placeholder="Enter new balance",
                id="edit-input",
                type="number",
            )
            yield Label("Enter to confirm | Escape to cancel", id="edit-hint")

    def on_mount(self) -> None:
        inp = self.query_one("#edit-input", Input)
        inp.focus()

    @on(Input.Submitted, "#edit-input")
    def on_submit(self, event: Input.Submitted) -> None:
        try:
            new_balance = float(event.value)
            if new_balance >= 0:
                self.dismiss((self.debt_name, new_balance))
            else:
                self.notify("Balance must be >= 0", severity="error")
        except ValueError:
            self.notify("Invalid number", severity="error")

    def action_cancel(self) -> None:
        self.dismiss(None)


# ── Entry Point ─────────────────────────────────────────────────────────────


def main() -> None:
    """Run the Debt Snowball TUI."""
    if len(sys.argv) < 2:
        # Try default path
        default_path = Path("data/debts_filled.csv")
        if default_path.exists():
            csv_path = str(default_path)
        else:
            print("Usage: python -m debt_snowball <path_to_debts.csv>")
            print("  or place a CSV at data/debts_filled.csv")
            sys.exit(1)
    else:
        csv_path = sys.argv[1]

    if not Path(csv_path).exists():
        print(f"Error: File not found: {csv_path}")
        sys.exit(1)

    app = DebtSnowballApp(csv_path)
    app.run()


if __name__ == "__main__":
    main()
