# Campus Customs MCP Server

A [FastMCP](https://gofastmcp.com) server that gives agents access to the Campus Customs shop database. It's the agent team's only source of shop facts (see `backend/`).

## Database

The server talks only to `data/campus_customs_new.db`. The original `data/campus_customs.db` is never touched and is kept for resets. If the working copy is missing, tool calls fail instead of creating an empty database.

Reset the working copy (from `hw5/`) before a full run to resolve the tickets. The dashboard's **Start over** button and `python backend/main.py --run-board` do this for you.

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

"Today" for the shop is `desk.date_today`, not the computer's clock. Every due-date and overdue calculation uses it.

## Tools

| Tool | Arguments | What it does |
| --- | --- | --- |
| `get_shop_date` | none | Returns `desk.date_today` and desk notes |
| `list_open_tickets` | none | Every unresolved ticket (oldest first) and the shop date |
| `list_tickets` | none | Every ticket with its status, resolved or not |
| `get_ticket` | `ticket_id` | One ticket, including notes and drafts |
| `update_ticket` | `ticket_id`, `status`, `note` | Sets status and appends a dated note |
| `save_draft` | `ticket_id`, `recipient`, `message` | Saves a draft on the ticket; nothing is sent |
| `check_stock` | `sku`, optional `size` | Units on hand per size, location, cost, and list price |
| `list_vendors` | none | Vendors with lead days, open invoices, and `can_ship` |
| `get_restock_eta` | `sku`, `size`, `qty`, `vendor_id` | Arrival date and cost, or what blocks the vendor; orders nothing |
| `quote_bulk_price` | `sku`, `qty`, optional `discount_pct` | Price and margin at a discount; changes nothing |
| `list_bills_due` | none | Unpaid invoices and rent with due/overdue info, plus cash |
| `get_lease` | `lease_id` | Lease details with days until due |
| `get_cash_balance` | optional `account` | One cash account's balance |
| `list_payments` | none | The payment ledger |
| `pay_invoice` | `invoice_id`, optional `account` | Pays an invoice after human approval |
| `pay_rent` | `lease_id`, optional `account` | Pays a month of rent after human approval |

Ticket statuses: `open`, `in_progress`, `waiting_on_vendor`, `waiting_on_human`, `resolved`.

See `output/harness.md` for which tickets each tool helps with.

## Rules the server enforces

These hold no matter which client calls the server:

- **Human approval for every payment.** `pay_invoice` and `pay_rent` first return an MCP input-required approval form showing the amount, payee, and balance before and after. The client must show it to a person, who accepts and types their name. The server then checks the answer and that the amount hasn't changed. If they decline, or the client can't show the form, nothing is paid.
- **No negative balances.** A payment the account can't cover is refused, and cash is re-checked inside the transaction that writes the payment.
- **Payments update the tables.** In one transaction: a row is added to `payments` (with `approved_by`), `cash_accounts` is reduced, and the invoice is marked `paid` or the lease's `next_due` moves forward a month. Paying a paid invoice is refused.
- **Blocked vendors.** `list_vendors` and `get_restock_eta` report a vendor with an open unpaid invoice as unable to ship.
- **Nothing is sent.** There are no email or call tools; `save_draft` keeps messages on the ticket.

## Setup

From `hw5/`:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Connecting

`hw5/.mcp.json` holds the connection config (stdio, using the hw5 venv's Python). Claude Code loads it in a session opened on the `hw5` folder, and `backend/models.py` reads the same file to connect the agents. To run the server by hand:

```bash
python mcp_server/server.py
```
