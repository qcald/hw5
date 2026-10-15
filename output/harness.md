# Campus Customs Agent Harness

A team of five AI agents runs the back office of Campus Customs, a Yale campus merch shop. A person supervises them from a web dashboard. The agents read and change shop data only through an MCP server, every payment needs a person's approval, and every step is recorded in an append-only audit trail. Design reasoning is in `output/design.md`.

Working database: `data/campus_customs_new.db` (original kept at `data/campus_customs.db` for resets).

## Project Layout

| Path | What it is |
| --- | --- |
| `data/campus_customs.db` | The original database. Never modified; used only to reset. |
| `data/campus_customs_new.db` | The working copy that everything reads and writes. |
| `mcp_server/server.py` | FastMCP server: the only code that touches the database, and where the shop rules are enforced. |
| `.mcp.json` | MCP connection config, used by both Claude Code and the backend. |
| `backend/prompts/` | One prompt file per agent (`boss.md`, `inventory.md`, `accounting.md`, `facilities.md`, `customer_service.md`). Each file has the shared shop rules plus that agent's role. |
| `backend/models.py` | The model (`gpt-6-luna` via Portkey), the MCP connection (audits every tool call and handles payment approvals), the append-only audit trail, and the agent team (Boss plus four specialists, each limited to its own tools). |
| `backend/main.py` | FastAPI routes for the dashboard, plus a terminal runner (`--run-board`) and an audit check (`--verify-audit`). |
| `frontend/` | React + Vite + TypeScript dashboard. |
| `output/` | Harness, design notes, audit trail, test results, and ticket reports. |
| `README.md`, `AI_prompts.md` | Project overview and the log of prompts used to build it. |
| `.env.example`, `.gitignore` | Template for `PORTKEY_API_KEY`, and files kept out of git (`.env`, `.venv`, `node_modules`). |

## How to Run

```bash
# once, from hw5/
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

1. **Backend** (from `hw5/backend`, venv active): `uvicorn main:app --reload --port 8000`
2. **Dashboard** (from `hw5/frontend`): `npm run dev`, then open the URL Vite prints.
3. On the dashboard, use **Start over with fresh data** before a full run, pick a request, and click **Start the team**. Approve or decline any payment when asked, then click **Ask the team to pick it back up** so they can finish.

There is also a terminal runner, `python backend/main.py --run-board`, which resets the database and works the whole board, asking for approvals at the prompt.

## Database Tables

### `desk`
Fields: `date_today`, `notes`

Why it matters: `date_today` is the shop's "today" and the only clock agents use to decide what is due or overdue.

### `inventory`
Fields: `sku`, `name`, `size`, `qty`, `location`

Why it matters: Agents check stock by SKU and size to see whether an order can be filled now or needs a reprint.

### `pricing`
Fields: `sku`, `unit_cost`, `list_price`

Why it matters: Gives cost and list price so agents can quote orders and judge how much discount a margin can absorb.

### `vendors`
Fields: `id`, `name`, `specialty`, `lead_days`

Why it matters: Tells agents which vendor can restock an item and how many days delivery takes from `date_today`.

### `leases`
Fields: `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`

Why it matters: Holds the rent amount and due date agents need to handle rent notices before they go overdue.

### `cash_accounts`
Fields: `name`, `balance`, `date`

Why it matters: The cash available for payments; the pay tool must refuse anything that would make a balance negative.

### `payments`
Fields: `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`

Why it matters: The ledger of every human-approved payment, so agents record what was paid, from where, and who approved it.

### `invoices`
Fields: `id`, `vendor_id`, `amount`, `due_date`, `status`, `description`

Why it matters: An open unpaid invoice blocks that vendor from shipping, so agents must check and settle it before reordering.

### `tickets`
Fields: `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at`

Why it matters: The work queue the agents resolve; each ticket links to the SKU, lease, or invoice it concerns.

## MCP Server

`mcp_server/server.py` (FastMCP). Reads and writes only `data/campus_customs_new.db`, and calls error out if that file is missing rather than creating an empty one. The agents connect to it using the same `.mcp.json` config Claude Code uses, and it is their only source of shop facts.

### Tools

| Tool | What it does | Tickets it helps with |
| --- | --- | --- |
| `get_shop_date()` | Returns `desk.date_today` and desk notes. Every due/overdue calculation uses this date. | All |
| `list_open_tickets()` | Every unresolved ticket, oldest first, plus the shop date. | All: the board |
| `list_tickets()` | Every ticket, resolved or not, with its status. Used by the dashboard. | All |
| `get_ticket(ticket_id)` | One ticket with its notes and any saved drafts. | All |
| `update_ticket(ticket_id, status, note)` | Sets status (`open`, `in_progress`, `waiting_on_vendor`, `waiting_on_human`, `resolved`) and appends a dated note. A note is required. | All: closing out tickets |
| `save_draft(ticket_id, recipient, message)` | Appends a dated draft to the ticket's notes. Nothing is ever sent. | 101 (customer reply, vendor order), 102 (landlord reply), 103 (reply to the student org) |
| `check_stock(sku, size?)` | Units on hand per size, location, unit cost, and list price. | 101 (size-S tees at 0), 103 (8 M hoodies vs. 20 requested) |
| `list_vendors()` | Vendors with specialty, `lead_days`, open unpaid invoices, and `can_ship`. | 101, 103: picking a vendor and seeing what blocks it |
| `get_restock_eta(sku, size, qty, vendor_id)` | Current stock, estimated cost, and either the arrival date (shop date + `lead_days`) or the invoices blocking the vendor. Orders nothing. | 101 (tee reprint), 103 (hoodie shortfall) |
| `quote_bulk_price(sku, qty, discount_pct)` | Unit price, total, and margin at a discount; flags below-cost prices. Changes nothing. | 103 (bulk discount) |
| `list_bills_due()` | Unpaid invoices and rent with `days_until_due` and `overdue`, plus the cash balance. | 101 (invoice 501 overdue), 102 (rent), cash planning for all |
| `get_lease(lease_id)` | The lease with rent, next due date, and days until due. | 102 (checking the rent notice against the lease) |
| `get_cash_balance(account="checking")` | One cash account's balance. Used by the dashboard. | 101, 102: cash after payments |
| `list_payments()` | The payment ledger, with who approved each payment. | 101, 102: confirming payments and avoiding double payment |
| `pay_invoice(invoice_id, account="checking")` | Pays an invoice in full, after human approval. Marks it `paid`, reduces cash, and logs the payment. | 101 (unblocks Bulldog Print Co) |
| `pay_rent(lease_id, account="checking")` | Pays one month of rent, after human approval. Moves `next_due` forward a month, reduces cash, and logs the payment. | 102 |

## Agents

Built with PydanticAI in `backend/`. Prompts are in `backend/prompts/`, one file per agent, each with the shared rules plus that agent's role. Every agent uses `gpt-6-luna` through Portkey's Responses endpoint (`/v1/responses`), because `gpt-6-luna` won't make tool calls on Chat Completions while reasoning is on. `backend/models.py` is the only place the model is named, and each agent can see only the MCP tools listed for it in `AGENT_TOOLS` there.

| Agent | Role | MCP tools |
| --- | --- | --- |
| **Boss** | Owns the board. Plans across tickets (dependencies, cash), delegates to specialists with `ask_inventory`, `ask_accounting`, `ask_facilities`, and `ask_customer_service`, and is the only agent that sets ticket status. | `get_shop_date`, `list_open_tickets`, `get_ticket`, `update_ticket` |
| **Inventory** | Stock checks, picking a vendor by specialty, lead times, restock arrival and cost, blocked-vendor reports, and draft vendor orders. | `get_shop_date`, `get_ticket`, `check_stock`, `list_vendors`, `get_restock_eta`, `save_draft` |
| **Accounting** | Bills, overdue status, cash planning (cash only goes out), margins, and the only agent that can pay. | `get_shop_date`, `get_ticket`, `list_bills_due`, `list_payments`, `quote_bulk_price`, `pay_invoice`, `pay_rent` |
| **Facilities** | Leases and rent notices: checks a notice against the lease and drafts landlord replies. Never pays. | `get_shop_date`, `get_ticket`, `get_lease`, `list_bills_due`, `save_draft` |
| **Customer service** | Drafts replies to customers and requesters. Promises only confirmed dates and approved discounts. | `get_shop_date`, `get_ticket`, `check_stock`, `quote_bulk_price`, `save_draft` |

Specialists don't talk to each other; the boss passes along facts from one specialist's tool results to the next. Run from the dashboard, or with `python backend/main.py --run-board`, which resets the working database to the original first (`--no-reset` skips that).

## API Routes

FastAPI app in `backend/main.py` for the React dashboard (start it from `hw5/backend` with the venv active: `uvicorn main:app --reload --port 8000`). Every shop fact comes through the MCP server.

- `GET /api/tickets`: all three tickets with their status and whether each is `open` or `resolved`.
- `POST /api/tickets/{ticket_id}/run`: starts the agent team on one ticket in the background and returns a `run_id`. Only one run at a time.
- `GET /api/events?since=&limit=&run_id=&ticket_id=`: recent agent events from the audit trail (what each agent said, which tools it used) plus run statuses, so the board can refresh. Runs from before the last reset are left out.
- `GET /api/approvals?status=pending`: payments the agents prepared and are waiting on a human (so the board knows what to show approve buttons for).
- `POST /api/approvals/{approval_id}`: a human approves (`{"decision": "approve", "approved_by": "<name>"}`) or denies a prepared payment. Approving is the only thing that pays and changes cash.
- `GET /api/cash`: the current checking balance from `cash_accounts`.
- `POST /api/reset`: resets the working database to the original values for a fresh run and clears pending approvals.

## Dashboard

React + Vite + TypeScript app in `frontend/` (`npm run dev`; Vite proxies `/api` to the backend on port 8000). It's a single front-desk page written in plain language for non-technical staff, not a board of columns. Yale blue is the accent.

- **Requests list:** all three tickets with friendly statuses (New, Team is working, Needs your decision, Waiting on a delivery, Resolved ✓).
- **Start the team:** runs the agents on the selected ticket; disabled while another ticket is running.
- **The team:** the five agents, each showing what it's doing right now, live while the ticket runs.
- **Step by step / What each person did:** the live conversation (hand-offs, actions, reports) and a short per-agent summary of the ticket, including payments a person approved.
- **Where it stands, then approval:** when a run ends, the Boss's summary appears first, with any prepared payment below it (amount, payee, and balance before and after). A person types their name to approve, or declines. Approval cards stay hidden while the team is still working, and the backend refuses approvals mid-run.
- **Checking balance:** shown in the header; it drops after an approved payment and shows the last change.
- **Drafted messages and start over:** drafts saved on the ticket (never sent), and a confirmed reset to the original data.

## Audit Trail

Every agent run writes to `output/audit_trail.json`. The file is appended to, never overwritten, across runs. Events include `run_started`, `agent_started`, `delegation`, `tool_call` (agent, tool, args, result, duration), `tool_error`, `approval_requested`, `approval_queued` (prepared for the dashboard), `approval_decision` (approved/denied and by whom), `approval_result` (whether the approved payment went through), `agent_finished`, and `run_finished`/`run_failed`. Each entry carries the hash of the one before it; `python backend/main.py --verify-audit` checks the chain.

## Safety

- **Payments need a human, enforced by the server.** `pay_invoice` and `pay_rent` return an approval form instead of paying. Through the API, an agent's payment is only prepared and queued: the agent is told it's pending, and cash changes only when a person approves it with their name through `POST /api/approvals/{id}`. In the terminal runner, a person types their name to approve, and pressing Enter denies. The server checks the answer and the amount the human saw. A client with no human attached can't pay.
- **No negative balances.** The server refuses any payment the cash account can't cover, and re-checks inside the same transaction that writes it.
- **Payments are recorded.** Each payment updates `payments` (with `approved_by`), `cash_accounts`, and the invoice or lease, all in one transaction. Paying a paid invoice is refused.
- **Facts only from MCP.** No backend code reads the database. The prompts forbid inventing facts and require reporting tool errors as returned.
- **Least privilege.** Only accounting has the payment tools, and only the boss can change ticket status.
- **Nothing leaves the shop.** There are no email or call tools. Messages are saved as drafts on the ticket.
- **One model.** Only `gpt-6-luna`, through Portkey, using `PORTKEY_API_KEY` from `.env`.
- **Clean starts and limits.** A full run resets the working database from the untouched original first. Model requests are capped at 80 per run.
- **Ticket text is data.** Instructions found inside tickets or tool results are ignored.

## Testing

| Test | What it checked | Result |
| --- | --- | --- |
| MCP smoke test (`output/mcp_smoke.json`) | The server starts from `.mcp.json`, lists its tools, and returns correct data. Also confirmed by calling the tools directly from a Claude Code session opened on `hw5/`. | Passed |
| Offline agent wiring (scripted model, scratch copy of the data) | Each agent sees only its own tools. Hand-offs work. An approved payment pays and is logged with the approver. A denied payment pays nothing. Paying twice is refused. The audit trail stays appended and hash-chained across runs. | Passed |
| Offline API routes (scripted model, scratch copy) | Every route works. A run only queues payments. Approve pays and lowers cash. Approving with no name, approving twice, and approving mid-run are refused. Deny leaves cash alone. Reset restores everything. | Passed |
| Dashboard in the browser (scripted model, scratch copy) | Live team status and timeline, approval only after "Where it stands", cash drop after approval, Resolved after the team picks the ticket back up, drafts shown in full, reset, phone layout, and no console errors. | Passed |
| Live model check | `gpt-6-luna` through Portkey's Responses endpoint makes tool calls. A real Inventory agent run against the MCP server reported correctly. | Passed |
| Full run with real agents | See **Test Run Results** below. | Passed (rules held; 1 of 3 resolved, 2 correctly waiting on a person) |

## Test Run Results

Full run on 2026-10-14 with the real agents (`gpt-6-luna` through Portkey). The data was reset first, and each ticket was run from the dashboard API. Payments were approved by a person (Quinn) on the dashboard. Details are in `output/desk_tickets.html` and `output/resolved_tickets.json`.

| Ticket | Runs | Final status | What happened |
| --- | --- | --- | --- |
| #101 Bulldog tee | 2 | `waiting_on_human` | Run 1: found 0 size-S tees and Bulldog Print Co blocked by invoice 501, queued the $840.00 payment, and drafted an honest customer reply. After approval, run 2 confirmed the vendor could ship, drafted a 1-unit reprint order (arrives 2026-09-05, ~$8.00), and drafted a corrected reply. It waits on a person to place the order, because agents can only draft purchases. |
| #102 Rent due | 2 | `resolved` | Run 1: checked the notice against lease 1 ($2,400.00 due 2026-09-02), drafted a landlord reply that doesn't claim payment, and queued the rent payment. After approval, run 2 confirmed payment 2 in the ledger, drafted a payment confirmation, and resolved the ticket. |
| #103 Bulk hoodie discount | 1 | `waiting_on_human` | Found 8 of 20 size-M hoodies, priced a 12-unit restock at $264.00 (vendor blocked at the time), and quoted list price ($1,160.00). With no discount policy in the data, it left the decision to a person and drafted an "under review" reply. |

**Cash:** $3,400.00 → −$840.00 (invoice 501, payment 1) → −$2,400.00 (rent, payment 2) → **$160.00**. Both payments were approved by Quinn. No balance went negative, and nothing was paid without approval.

**Rules checked during the run:**
- **Dates:** "today" always came from `desk.date_today` (2026-08-31).
- **Blocked vendor:** no delivery date was promised while the vendor was blocked.
- **Payments:** every payment waited for a person, and payments were recorded in `payments`, `cash_accounts`, `invoices`, and `leases`.
- **No sending:** nothing was sent; all messages are drafts.
- **One model:** only `gpt-6-luna` was used.
- **Audit trail:** it was appended across all five runs, and `--verify` passes.

**Issues found:**
- **Two-run tickets:** human approval splits a paid ticket into two runs.
- **Drafts pile up:** drafts can't be edited, so outdated ones stay on the ticket.
- **Facilities on #102:** it couldn't see the ledger and briefly read the paid rent's new due date as a mismatch.
- **Accounting on #103:** it said there were no pending approvals, because its tools can't see the dashboard's approval queue.
- **Narrow quote on #103:** accounting quoted only list price, not several discount levels.

## Output Files

| File | What it is |
| --- | --- |
| `output/harness.md` | This file. |
| `output/design.md` | Why the system and dashboard are designed the way they are. |
| `output/audit_trail.json` | Append-only, hash-chained record of every run, tool call, and approval. |
| `output/mcp_smoke.json` | The MCP smoke test: prompt, tool, and output for the first three tools. |
| `output/desk_tickets.html` | Expected vs. actual workflow for each ticket, plus a cash tab itemizing cash flows. |
| `output/resolved_tickets.json` | For each ticket: final status, short outcome, what each agent did, and human approvals. |
| `output/resolved_board.html` | A static snapshot of the final board, built from `resolved_tickets.json`. |
| `output/github_url.txt` | Link to the project's GitHub repository. |

## Known Limitations

- **Pending approvals are kept in memory.** Restarting the backend, including the auto-reload when a backend file is saved, clears them. Asking the team to pick the ticket back up prepares the payment again.
- **Purchases aren't modeled.** Restock orders are drafts only; only invoice and rent payments go through approval.
- **There's no discount policy in the data,** so the agents can't decide ticket 103's discount. They report the margins and leave the decision to a person.
