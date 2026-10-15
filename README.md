# Campus Customs Front Desk (HW5)

A team of five AI agents runs the back office of Campus Customs, a Yale campus merch shop:
- **The agents:** a Boss plus Inventory, Accounting, Facilities, and Customer Service.
- **Shop data:** they read and change it only through an MCP server.
- **Payments:** every payment waits for a person to approve it.
- **Record:** every step is recorded in an append-only audit trail.
- **Dashboard:** a person supervises everything from a React page.

## Folder structure

```
hw5/
├── AI_prompts.md            prompts used to build this project with an AI assistant
├── requirements.txt         Python dependencies
├── .env.example             copy to .env and add PORTKEY_API_KEY
├── .gitignore
├── .mcp.json                MCP connection config (used by Claude Code and the backend)
├── README.md
├── data/
│   ├── campus_customs.db        original data, never modified (used to reset)
│   └── campus_customs_new.db    working copy that everything reads and writes
├── mcp_server/
│   ├── server.py            FastMCP server: the only code that touches the database
│   └── README.md
├── frontend/                React + Vite + TypeScript dashboard
├── backend/
│   ├── main.py              FastAPI routes for the dashboard, plus a terminal runner
│   ├── models.py            model (gpt-6-luna via Portkey), MCP connection, audit trail, agent team
│   └── prompts/             one prompt per agent (boss, inventory, accounting, facilities, customer_service)
└── output/
    ├── harness.md           tables, tools, agents, routes, safety, testing, and run results
    ├── mcp_smoke.json       MCP smoke test
    ├── desk_tickets.html    expected vs. actual per ticket, cash flows, and reflections
    ├── design.md            design choices and why
    ├── resolved_tickets.json    final status, outcome, agent actions, and approvals per ticket
    ├── resolved_board.html  snapshot of the final board
    ├── audit_trail.json     append-only, hash-chained record of every run
    └── github_url.txt       repository link
```

## Setup

From `hw5/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then add your PORTKEY_API_KEY
cd frontend && npm install && cd ..
```

## Run

1. **Backend** (from `hw5/backend`, with the venv active): `uvicorn main:app --reload --port 8000`
2. **Dashboard** (from `hw5/frontend`): `npm run dev`, then open the URL Vite prints.
3. On the dashboard:
   1. Click **Start over with fresh data** before a full run.
   2. Pick a request and click **Start the team**.
   3. Approve or decline any payment when asked.
   4. Click **Ask the team to pick it back up** so they can finish.

Other commands (from `hw5/backend`):

```bash
python main.py --run-board      # reset the data and work every ticket in the terminal
python main.py --verify-audit   # check the audit trail's hash chain
```

## Homework rules

These come from the assignment and are enforced in the MCP server and backend.

**Database**
- All backend code reads and writes `data/campus_customs_new.db`.
- `data/campus_customs.db` is never modified.
- Reset before a full run: use **Start over** on the dashboard, `POST /api/reset`, or `cp data/campus_customs.db data/campus_customs_new.db`.

**Shop logic**
- **Today** is `desk.date_today`, never the computer's clock. It decides what is overdue.
- **Lead times** come from the `vendors` table.
- **Blocked vendors:** a vendor won't ship while it has an open unpaid invoice.
- **Approvals:** every payment needs a person's approval. Agents only prepare payments, and the dashboard's approve route is what changes cash.
- **Recording payments:** each payment updates `payments`, `cash_accounts`, and the invoice or lease.
- **No negative balances:** the pay tools refuse if there isn't enough cash.
- **Cash only goes out;** there's no revenue model.
- **Nothing is sent:** no emailing customers or calling vendors. Messages are drafts saved on the ticket.

**AI calls**
- **Key:** `PORTKEY_API_KEY` from `.env`, through the official `openai` package and Portkey.
- **Model:** only `gpt-6-luna`, for every agent. It's named once, in `backend/models.py`.

## More detail

- `output/harness.md`: every table, tool, agent, and route, plus safety, testing, and results.
- `output/design.md`: why the system and dashboard are designed the way they are.
- `mcp_server/README.md` and `frontend/README.md`: details for each part.
