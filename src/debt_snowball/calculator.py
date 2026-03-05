"""Core snowball calculation engine."""

from __future__ import annotations

import csv
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class Debt:
    """Represents a single debt."""

    name: str
    starting_balance: float
    current_balance: float
    apr: float
    minimum_payment: float

    @property
    def monthly_rate(self) -> float:
        return self.apr / 100.0 / 12.0

    @property
    def is_paid_off(self) -> bool:
        return self.current_balance < 0.005


@dataclass
class MonthPayment:
    """Payment details for a single debt in a single month."""

    debt_name: str
    payment_amount: float
    interest_charged: float
    principal_paid: float
    remaining_balance: float
    is_snowball_target: bool = False


@dataclass
class MonthSchedule:
    """All payments for a single month."""

    month_number: int
    date: datetime
    payments: list[MonthPayment] = field(default_factory=list)
    debts_paid_off: list[str] = field(default_factory=list)


@dataclass
class PayoffEvent:
    """When a debt gets paid off."""

    name: str
    month_number: int
    date: datetime
    total_paid: float


@dataclass
class SnowballResult:
    """Full result of a snowball calculation."""

    debts: list[Debt]
    schedule: list[MonthSchedule]
    payoff_events: list[PayoffEvent]
    total_interest_paid: float
    total_months: int
    monthly_budget: float
    extra_payment: float


def load_debts_from_csv(filepath: str | Path) -> list[Debt]:
    """Load debts from a CSV file."""
    debts = []
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            if not name:
                continue
            debts.append(
                Debt(
                    name=name,
                    starting_balance=float(row["starting_balance"]),
                    current_balance=float(row["current_balance"]),
                    apr=float(row["apr"]),
                    minimum_payment=float(row["minimum_payment"]),
                )
            )
    return debts


def save_debts_to_csv(filepath: str | Path, debts: list[Debt]) -> None:
    """Save debts back to a CSV file."""
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "name",
                "starting_balance",
                "current_balance",
                "apr",
                "minimum_payment",
            ],
        )
        writer.writeheader()
        for d in debts:
            writer.writerow(
                {
                    "name": d.name,
                    "starting_balance": d.starting_balance,
                    "current_balance": d.current_balance,
                    "apr": d.apr,
                    "minimum_payment": d.minimum_payment,
                }
            )


def calculate_snowball(
    debts: list[Debt],
    extra_monthly: float = 0.0,
    start_date: Optional[datetime] = None,
) -> SnowballResult:
    """Calculate the full debt snowball payment schedule.

    Args:
        debts: List of debts to pay off.
        extra_monthly: Extra money beyond minimums to throw at the snowball target.
        start_date: When payments start (defaults to next month's 1st).

    Returns:
        SnowballResult with full schedule and summary.
    """
    if start_date is None:
        now = datetime.now()
        if now.month == 12:
            start_date = datetime(now.year + 1, 1, 1)
        else:
            start_date = datetime(now.year, now.month + 1, 1)

    # Sort by current balance (smallest first) for snowball method
    working_debts = sorted(deepcopy(debts), key=lambda d: d.current_balance)

    # Filter out already paid-off debts
    active_debts = [d for d in working_debts if not d.is_paid_off]
    if not active_debts:
        return SnowballResult(
            debts=working_debts,
            schedule=[],
            payoff_events=[],
            total_interest_paid=0.0,
            total_months=0,
            monthly_budget=0.0,
            extra_payment=extra_monthly,
        )

    monthly_budget = sum(d.minimum_payment for d in active_debts) + extra_monthly
    total_interest = 0.0
    schedule: list[MonthSchedule] = []
    payoff_events: list[PayoffEvent] = []
    total_paid_per_debt: dict[str, float] = {d.name: 0.0 for d in active_debts}
    paid_off_names: set[str] = set()

    month = 0
    max_months = 600  # 50-year safety limit

    while any(not d.is_paid_off for d in active_debts) and month < max_months:
        month += 1
        current_date = start_date + timedelta(days=30 * (month - 1))
        month_schedule = MonthSchedule(month_number=month, date=current_date)
        remaining_budget = monthly_budget

        # 1. Apply interest to all active debts
        interest_this_month: dict[str, float] = {}
        for d in active_debts:
            if not d.is_paid_off:
                interest = d.current_balance * d.monthly_rate
                d.current_balance += interest
                total_interest += interest
                interest_this_month[d.name] = interest

        # 2. Pay minimums on all debts
        for d in active_debts:
            if not d.is_paid_off:
                payment = min(d.minimum_payment, d.current_balance)
                d.current_balance -= payment
                remaining_budget -= payment
                total_paid_per_debt[d.name] = total_paid_per_debt.get(d.name, 0.0) + payment
                interest = interest_this_month.get(d.name, 0.0)
                principal = payment - interest
                month_schedule.payments.append(
                    MonthPayment(
                        debt_name=d.name,
                        payment_amount=payment,
                        interest_charged=interest,
                        principal_paid=max(0, principal),
                        remaining_balance=max(0, d.current_balance),
                        is_snowball_target=False,
                    )
                )

        # 3. Apply remaining budget to the smallest balance (snowball target)
        for d in active_debts:
            if not d.is_paid_off and remaining_budget > 0.005:
                extra = min(remaining_budget, d.current_balance)
                if extra > 0.005:
                    d.current_balance -= extra
                    remaining_budget -= extra
                    total_paid_per_debt[d.name] = total_paid_per_debt.get(d.name, 0.0) + extra
                    # Update the existing payment entry for this debt
                    for mp in month_schedule.payments:
                        if mp.debt_name == d.name:
                            mp.payment_amount += extra
                            mp.principal_paid += extra
                            mp.remaining_balance = max(0, d.current_balance)
                            mp.is_snowball_target = True
                            break
                break  # Only apply extra to the first (smallest) unpaid debt

        # 4. Check for payoffs
        for d in active_debts:
            if d.is_paid_off and d.name not in paid_off_names:
                d.current_balance = 0.0
                paid_off_names.add(d.name)
                month_schedule.debts_paid_off.append(d.name)
                payoff_events.append(
                    PayoffEvent(
                        name=d.name,
                        month_number=month,
                        date=current_date,
                        total_paid=total_paid_per_debt.get(d.name, 0.0),
                    )
                )

        schedule.append(month_schedule)

    return SnowballResult(
        debts=active_debts,
        schedule=schedule,
        payoff_events=payoff_events,
        total_interest_paid=total_interest,
        total_months=month,
        monthly_budget=monthly_budget,
        extra_payment=extra_monthly,
    )
