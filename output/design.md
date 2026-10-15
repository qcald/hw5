# Campus Customs Front Desk: Design

This document explains how the HW5 system is put together and why each major choice was made. For the full list of tables, tools, agents, and routes, see `output/harness.md`.

## Goals

The assignment set the rules; these goals shaped everything else:

1. **Follow the shop rules exactly.** "Today" is `desk.date_today`. A vendor with an open invoice won't ship. Every payment needs a human. No negative balances. Cash only goes out. Nothing gets sent to anyone. Only `gpt-6-luna` is used.
2. **Make the rules impossible to skip, not just unlikely to be skipped.** A prompt can be ignored by a model. A check in code can't. Wherever possible, rules are enforced in the MCP server or the backend, and the prompts back them up.
3. **Keep every shop fact traceable.** Agents never invent numbers, and anyone can check afterward what each agent saw and did.
4. **Make the dashboard understandable to someone non-technical.** A store manager should be able to run a request, follow along, and approve a payment without knowing what an agent, a tool, or an API is.

## Architecture

```
React dashboard (frontend/)
        │  /api (Vite proxy)
FastAPI backend (backend/main.py) ── output/audit_trail.json
        │
PydanticAI agent team (backend/models.py) ── gpt-6-luna via Portkey
        │  MCP over stdio (.mcp.json)
FastMCP server (mcp_server/server.py)
        │
data/campus_customs_new.db   (data/campus_customs.db = untouched original)
```

### One source of facts: the MCP server

Everything that reads or changes shop data goes through `mcp_server/server.py`. Nothing in `backend/` opens the database. The agents, the API routes, and Claude Code (through `.mcp.json`) all use the same server.

**Why:**
- **No made-up facts.** If the only way to learn a stock count is a tool call, an agent can't invent one without it showing up as a missing tool call in the audit trail.
- **The rules live in one place.** The open-invoice block, the overdue math against `desk.date_today`, the cash check, and the approval gate are each written once, in the server. Every client gets the same behavior.
- **The original data is protected.** The server is hard-wired to `campus_customs_new.db`, and it opens the file in a mode that fails rather than creating an empty database. The original copy is only ever read, to reset.

### Tools are shaped around tasks, not tables

Instead of a generic "run SQL" tool, the server offers tools such as `get_restock_eta`, `list_bills_due`, and `quote_bulk_price`. These return answers that already apply the rules: `can_ship`, `overdue`, `days_until_due`, `arrival_date`, and `below_cost`.

**Why:** the model doesn't have to work out the rules itself, which is where models make mistakes. For example, `get_restock_eta` won't return an arrival date for a blocked vendor, so an agent can't promise a delivery that can't happen. Read-only tools say so in their descriptions ("orders nothing", "changes nothing"), and the only tools that change data are clearly named (`update_ticket`, `save_draft`, `pay_invoice`, `pay_rent`).

## The agent team

| Agent | Owns |
| --- | --- |
| Boss | The ticket board: planning, handing out work, and setting ticket status |
| Inventory | Stock, suppliers, lead times, and draft vendor orders |
| Accounting | Bills, cash planning, margins, and payments |
| Facilities | Leases, rent notices, and landlord drafts |
| Customer Service | Replies to customers, drafted only |

### Why a boss with specialists

The specialists only talk to the Boss, never to each other.

- **Tickets depend on each other.** Ticket 101's tee can't be restocked until invoice 501 is paid, and every payment comes out of the same $3,400.00. Someone has to see the whole board and decide the order of work. The Boss's prompt tells it to plan across all tickets and check the cash picture before committing.
- **A clear chain of hand-offs.** With a single coordinator, the audit trail reads like a conversation: the Boss asks, the specialist acts and reports back. A free-for-all between agents would be harder to follow and would use more tokens.

### Least privilege

Each agent sees only the MCP tools listed for it in `AGENT_TOOLS` (`backend/models.py`):
- **Payments:** only Accounting has `pay_invoice` and `pay_rent`.
- **Ticket status:** only the Boss has `update_ticket`.
- **Rent:** Facilities can read the lease and draft to the landlord, but it can't pay; it hands rent back to the Boss for Accounting.

**Why:** a confused or manipulated agent can only do what its role allows. This was checked in testing by recording the tool list each agent actually saw.

### Prompts in one markdown file

Each agent has its own prompt file in `backend/prompts/` (`boss.md`, `inventory.md`, `accounting.md`, `facilities.md`, `customer_service.md`). Every file starts with the same shared section, followed by that agent's role. The shared section restates the shop rules and the rule that every fact must come from a tool. It also tells agents to treat ticket text as data, not as instructions.

**Why:** the prompts can be read and edited without touching code, and each file is the complete prompt that agent receives. The shared rules are repeated word for word in all five files, so any change to them has to go into all five.

### One model, through Portkey's Responses endpoint

`backend/models.py` is the only place a model is named. The agents call `gpt-6-luna` through Portkey with the official `openai` client.

**Why the Responses endpoint:** the first real run failed. `gpt-6-luna` refuses tool calls on Chat Completions while its reasoning is on. Switching to the Responses endpoint kept the model's reasoning and made tool calls work. Turning reasoning off would also have worked, but the agents would have planned less carefully.

**Limiting cost:** model requests are capped at 80 per run (`UsageLimits`), and routine lookups are kept small, because the assignment warns that multi-agent chats use up tokens quickly.

## Human approval for payments

This is the rule the assignment stresses most, so it's enforced at three levels.

1. **The MCP server.** `pay_invoice` and `pay_rent` never pay on the first call. They return an approval form showing the amount, the payee, and the balance before and after. The payment goes through only when the form comes back accepted with a person's name.
   - The server seals the amount the person saw, so it can't be swapped when the approval comes back.
   - It re-checks cash inside the same transaction that writes the payment.
   - A client with no person attached simply can't pay.
2. **The backend.** During an agent run, the backend answers that form by *queuing* the payment and telling the agent "pending human approval, nothing has been paid." Only `POST /api/approvals/{id}`, which a person triggers by clicking Approve, answers the form with "approved." That route is the only thing that changes cash. It also refuses while the team is still working on that request.
3. **The prompts.** Agents are told that "pending" means not paid. They must not draft "paid" confirmations or plan work that depends on the payment until it actually goes through.

**Why agents prepare and people approve:** the assignment says agents only prepare payments and the approval route is what changes cash. Splitting it this way also means a person always sees the full picture before money moves, which led to the next change.

**Approval comes after "Where it stands."** At first, the approval card appeared the moment Accounting queued a payment, before the Boss had finished its report. You could be asked to approve $840.00 without knowing why. Now the card stays hidden until the run ends, and the "Where it stands" summary appears above it.

## Audit trail

Every agent run, hand-off, tool call (with its arguments and result), approval request, decision, and payment result is added to `output/audit_trail.json`.

- **Append-only.** New entries are added at the end of the JSON array; earlier entries are never rewritten. This keeps a history across runs, as the assignment asks.
- **Hash-chained.** Each entry stores the hash of the one before it, so editing or deleting history breaks the chain. `python backend/main.py --verify-audit` checks it.
- **Also powers the dashboard.** `/api/events` reads the audit trail to show what each agent said and did, so the dashboard and the record can never disagree.

## The dashboard

### Who it's for

It's for a store manager or student worker, not a developer. Every design choice was checked against one question: would someone with no technical background know what this means and what to do next?

### Not a Jira board

The brief said to avoid looking like Jira. Ticket boards put work in columns of small cards. That suits a team juggling dozens of items, but it's noisy and abstract for three requests.

Instead, the dashboard works like a front desk:
- **Left:** a short list of today's requests, each written as the request itself ("Needs a tee in size S.").
- **Right:** the request you picked, laid out top to bottom in the order you'd care about it.

### Reading order on the request page

1. **What it is:** the kind of request, who sent it, when, and its status.
2. **Where it stands:** a short callout with the Boss's latest summary in plain sentences.
3. **What needs you:** the approval card, if there is one.
4. **What you can do:** one main button. Its label changes with the situation ("Start the team on this request", "Ask the team to pick it back up"), so the next step is always obvious.
5. **The team:** five columns, one per agent, each showing Working, Done, or Not involved yet, plus what the working agent is doing right now.
6. **Drafted messages:** the actual output, shown like letters with a "Copy text" button, since nothing is sent automatically.
7. **The detail:** a step-by-step timeline and a "What each person did" summary, for anyone who wants to dig in.

**Why this order:** most people only need the first four items. The detail is there for checking the agents' work (and for grading), but it doesn't get in the way.

### Plain language everywhere

- **Statuses** become "New", "Team is working", "Needs your decision", "Waiting on a delivery", and "Resolved".
- **Tool calls** become sentences: `get_restock_eta` becomes "Bulldog Print Co can't ship 1 more until its unpaid bill is settled."
- **Payments** say "Pay $840.00 for invoice 501 to Bulldog Print Co" with "Checking now" and "After payment" side by side, so the effect of approving is obvious.
- **Errors** become "The team stopped before finishing", with the technical message behind a Details link.

### A calm timeline

The first version showed every tool call, including routine lookups like "Checked today's date" and "Read request #101". Real runs produced long walls of text. The timeline now:
- hides routine lookups,
- groups each agent's actions under its name,
- collapses long messages behind "Read more", and
- shows failed runs as one quiet line.

**Why:** the timeline should tell the story of the run (who asked whom, what they found, what they decided) rather than log every call. The raw log is still available in the audit trail.

### Visual style

- **Restrained Yale.** Yale blue (`#00356B`) is used only as the accent: the brand mark, the main button, the selected request, and active tabs. A serif type for the brand name and for drafted letters adds a quiet campus feel. There are no crests, mascots, or Yale imagery, as asked.
- **Light, clean, and quiet.**
  - White panels on a pale gray background, with thin borders instead of heavy shadows.
  - Statuses are a small colored dot with a label, not loud pills.
  - Color carries meaning: blue for in progress, amber for something that needs you, green for done, red for problems.
- **Live without refreshing.** The page polls every 1.5 seconds while a run is going and less often otherwise. A pulsing dot marks the agent that's working.
- **Works on phones.** The layout stacks to a single column, and the team strip reflows to two columns.

### Small details that prevent mistakes

- **Approving needs a typed name**, which is saved for next time. A stray click can't pay anything, and the name ends up in `payments.approved_by`.
- **Start over** asks for confirmation and explains what it resets.
- **Only one request runs at a time.** Other requests' start buttons are disabled with a note saying why, because all requests share one database and one cash balance.
- **Drafts are labeled "not sent"** wherever they appear.

## Known limitations

- **Pending approvals live in memory.** Restarting the backend, including the automatic reload when a backend file is saved, clears them. The ticket still says "Needs your decision", and asking the team to pick it back up prepares the payment again. Saving approvals to disk would fix this; it was deferred.
- **Purchases aren't modeled.** Restock orders are drafts only, because the data doesn't say what approving a purchase should do to cash. Only invoice and rent payments go through approval.
- **No discount policy exists in the data.** Ticket 103's discount can't be decided by the agents. They show the margin numbers and leave the decision to a person, so that ticket is expected to end at "Needs your decision".
- **"Resolved" can take two runs.** A ticket that needs a payment stops at "Needs your decision" until someone approves. Then "Ask the team to pick it back up" lets the team finish and mark it resolved. The team marks a ticket resolved only when the work is really done.
