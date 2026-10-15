# Campus Customs Front Desk (dashboard)

React + Vite + TypeScript dashboard for the Campus Customs agent team. It talks only to the FastAPI backend in `../backend` (Vite proxies `/api` to `http://localhost:8000`).

## Run it

Start the backend first (from `hw5/backend`, with the venv active):

```bash
uvicorn main:app --reload --port 8000
```

Then, from `hw5/frontend`:

```bash
npm install
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173).

## What's on the page

- **Today's requests:** the three tickets, each with a plain-language status (New, Team is working, Needs your decision, Waiting on a delivery, Resolved).
- **Start the team:** runs the agent team on the selected request. Only one request runs at a time.
- **The team:** the five agents and what each one is doing right now, updated live while the team works.
- **Step by step:** a running conversation of who asked whom to do what, the actions each agent took, and their reports.
- **What each person did:** a short summary per agent, plus any payments you approved.
- **Your OK is needed:** when the team prepares a payment, it waits here. Type your name and approve, or decline. Money only leaves the account when you approve.
- **Checking account:** the balance in the header. It drops after an approved payment and shows the last change.
- **Messages drafted:** drafts the team wrote for the request. They're saved on the ticket and never sent.
- **Start over with fresh data:** resets the database to the original values. The audit history is kept.
