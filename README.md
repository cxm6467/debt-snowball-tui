# Debt Snowball TUI

A terminal user interface for calculating and tracking debt snowball payments. Works in any shell (zsh, bash, fish, etc.).

## Features

- **Editable balances** — Update current balances directly in the TUI; all calculations update automatically
- **Snowball schedule** — Full month-by-month payment schedule with interest/principal breakdown
- **Payoff timeline** — See when each debt will be paid off
- **Extra payment support** — Add extra monthly payments to accelerate payoff
- **Save to CSV** — Persist balance changes back to your CSV file
- **Shell-agnostic** — Works in zsh, bash, fish, or any terminal emulator

## Installation

```bash
uv sync
```

## Usage

```bash
# Run with default data file (data/debts_filled.csv)
uv run debt-snowball

# Run with a specific CSV file
uv run debt-snowball path/to/your/debts.csv
```

### CSV Format

```csv
name,starting_balance,current_balance,apr,minimum_payment
Chase Visa,5000,4500,18.99,100
Car Loan,15000,12000,4.5,350
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `E` | Edit selected debt's balance |
| `S` | Save current balances to CSV |
| `R` | Force recalculate |
| `Q` | Quit |

## How the Snowball Method Works

1. List debts from smallest balance to largest
2. Pay minimum payments on all debts
3. Throw all extra money at the smallest balance
4. When the smallest is paid off, roll that payment into the next smallest
5. Repeat until debt-free
