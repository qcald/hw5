"""FastAPI backend for the Campus Customs dashboard, plus a terminal runner.

    cd backend && source ../.venv/bin/activate && uvicorn main:app --reload --port 8000

    python main.py --run-board             # reset the data, then work every open ticket in the terminal
    python main.py --run-board --no-reset  # same, keeping the current data
    python main.py --verify-audit          # check output/audit_trail.json's hash chain

Every shop fact comes from the campus-customs MCP server; this file never reads the database.
Agents only prepare payments: when one calls pay_invoice or pay_rent, the payment is queued here as a
pending approval and nothing is paid. POST /api/approvals/{id} with decision "approve" is the only
thing that answers the server's approval form, so it is what actually changes cash.
"""

import argparse
import asyncio
import json
import shutil
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models import (
    AUDIT_PATH,
    MODEL_NAME,
    ORIGINAL_DB,
    USAGE_LIMITS,
    WORKING_DB,
    AgentDeps,
    PendingApproval,
    append_event,
    build_mcp_toolset,
    build_team,
    call_as_human,
    set_approver,
    verify_audit,
)

mcp = build_mcp_toolset()
team = build_team(mcp)

runs: dict[str, dict[str, Any]] = {}  # run_id -> run status
approvals: dict[str, dict[str, Any]] = {}  # approval_id -> pending/decided payment
_approval_lock = asyncio.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def active_run() -> dict[str, Any] | None:
    return next((r for r in runs.values() if r["status"] == "running"), None)


async def queue_for_dashboard(message: str, deps: AgentDeps, tool: str, args: dict[str, Any]) -> PendingApproval:
    """Approver used during agent runs: record the payment for a human to decide later; pay nothing now."""
    async with _approval_lock:
        for a in approvals.values():  # same payment already waiting: reuse it
            if a["status"] == "pending" and a["tool"] == tool and a["args"] == args:
                return PendingApproval(a["approval_id"])
        approval_id = uuid.uuid4().hex[:8]
        approvals[approval_id] = {
            "approval_id": approval_id,
            "status": "pending",
            "tool": tool,
            "args": args,
            "message": message,
            "requested_by": deps.agent,
            "run_id": deps.run_id,
            "ticket_id": deps.ticket_id,
            "created_at": now(),
        }
    return PendingApproval(approval_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    set_approver(queue_for_dashboard)
    async with mcp:
        yield


app = FastAPI(title="Campus Customs Desk API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def mcp_call(tool: str, args: dict[str, Any] | None = None) -> Any:
    result = await mcp.direct_call_tool(tool, args or {})
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ---------- Tickets ----------


@app.get("/api/tickets")
async def list_tickets() -> dict:
    """The tickets on the board, each marked open or resolved."""
    board = await mcp_call("list_tickets")
    tickets = [
        {
            "id": t["id"],
            "type": t["type"],
            "requester": t["requester"],
            "subject": t["subject"],
            "status": t["status"],
            "state": "resolved" if t["status"] == "resolved" else "open",
            "notes": t["notes"],
            "created_at": t["created_at"],
        }
        for t in board["tickets"]
    ]
    return {"shop_date": board["shop_date"], "tickets": tickets}


async def _run_ticket(run_id: str, ticket_id: int, task: str) -> None:
    run = runs[run_id]
    try:
        append_event(run_id, "boss", "agent_started", task=task, ticket_id=ticket_id)
        result = await team.boss.run(
            task, deps=AgentDeps(run_id=run_id, agent="boss", ticket_id=ticket_id), usage_limits=USAGE_LIMITS
        )
        append_event(run_id, "boss", "agent_finished", output=result.output)
        usage = result.usage
        run.update(status="finished", output=result.output, requests=usage.requests)
        append_event(
            run_id, "harness", "run_finished", ticket_id=ticket_id,
            requests=usage.requests, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
        )
    except Exception as e:
        run.update(status="failed", error=f"{type(e).__name__}: {e}")
        append_event(run_id, "harness", "run_failed", ticket_id=ticket_id, error=run["error"])
    run["finished_at"] = now()


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int) -> dict:
    """Start the agent team on one ticket. Runs in the background; poll /api/events for progress."""
    if (current := active_run()) is not None:
        raise HTTPException(status_code=409, detail=f"Run {current['run_id']} is still in progress")
    ticket = await mcp_call("get_ticket", {"ticket_id": ticket_id})
    if ticket["status"] == "resolved":
        raise HTTPException(status_code=409, detail=f"Ticket {ticket_id} is already resolved")

    run_id = uuid.uuid4().hex[:12]
    task = f"Work on ticket {ticket_id} only. Resolve it following your instructions and don't change any other ticket."
    runs[run_id] = {"run_id": run_id, "ticket_id": ticket_id, "status": "running", "started_at": now()}
    append_event(run_id, "harness", "run_started", model=MODEL_NAME, ticket_id=ticket_id, task=task)
    runs[run_id]["task"] = asyncio.create_task(_run_ticket(run_id, ticket_id, task))
    return {"run_id": run_id, "ticket_id": ticket_id, "status": "running"}


# ---------- Agent events ----------


def _summarize(e: dict[str, Any]) -> dict[str, Any]:
    """Shape an audit entry for the board: who, what they said, which tool they used."""
    said = e.get("output") or e.get("task") or e.get("message") or e.get("error")
    out = {k: e[k] for k in ("seq", "ts", "run_id", "agent", "event") if k in e}
    for k in ("tool", "args", "result", "to", "ticket_id", "approval_id", "decision", "approved_by", "paid"):
        if k in e:
            out[k] = e[k]
    if said is not None:
        out["said"] = said
    return out


def _runs_from_audit(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Ticket runs rebuilt from the audit trail, so history survives a backend restart."""
    found: dict[str, dict[str, Any]] = {}
    for e in entries:
        if e["agent"] == "harness" and e["event"] == "db_reset":
            found.clear()  # a reset starts a fresh board; older runs stay in the audit file only
            continue
        if e["agent"] != "harness" or "ticket_id" not in e:
            continue
        if e["event"] == "run_started":
            live = runs.get(e["run_id"])
            found[e["run_id"]] = {
                "run_id": e["run_id"],
                "ticket_id": e["ticket_id"],
                "started_at": e["ts"],
                # No finish event and not running in this process means the backend stopped mid-run.
                "status": "running" if live and live["status"] == "running" else "interrupted",
            }
        elif e["event"] in ("run_finished", "run_failed") and e["run_id"] in found:
            found[e["run_id"]].update(
                status="finished" if e["event"] == "run_finished" else "failed",
                finished_at=e["ts"],
                error=e.get("error"),
            )
    return found


@app.get("/api/events")
async def recent_events(
    since: int = Query(0, description="Only events with seq greater than this"),
    limit: int = Query(100, ge=1, le=500),
    run_id: str | None = None,
    ticket_id: int | None = Query(None, description="Only events from runs on this ticket"),
) -> dict:
    """Recent agent events (what each agent said, which tools they used) plus run statuses, for refreshing the board."""
    entries = json.loads(AUDIT_PATH.read_text() or "[]") if AUDIT_PATH.exists() else []
    ticket_runs = _runs_from_audit(entries)
    if ticket_id is not None:
        wanted = {r for r, info in ticket_runs.items() if info["ticket_id"] == ticket_id}
        ticket_runs = {r: info for r, info in ticket_runs.items() if r in wanted}
    else:
        wanted = None
    events = [
        e for e in entries
        if e["seq"] > since
        and (run_id is None or e["run_id"] == run_id)
        and (wanted is None or e["run_id"] in wanted)
    ]
    return {
        "events": [_summarize(e) for e in events[-limit:]],
        "last_seq": entries[-1]["seq"] if entries else 0,
        "runs": list(ticket_runs.values())[-10:],
    }


# ---------- Approvals ----------


@app.get("/api/approvals")
async def list_approvals(status: str | None = "pending") -> list[dict]:
    """Payments the agents prepared, by status (pending by default; pass status= for all)."""
    return [a for a in approvals.values() if not status or a["status"] == status]


class Decision(BaseModel):
    decision: Literal["approve", "deny"]
    approved_by: str = ""


@app.post("/api/approvals/{approval_id}")
async def decide_approval(approval_id: str, body: Decision) -> dict:
    """A human approves or denies a prepared payment. Approving is what actually pays and changes cash."""
    async with _approval_lock:
        approval = approvals.get(approval_id)
        if not approval:
            raise HTTPException(status_code=404, detail=f"No approval {approval_id}")
        if approval["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"Approval {approval_id} is already {approval['status']}")
        run = runs.get(approval["run_id"])
        if run and run["status"] == "running":
            # A human decides only after the team has finished and reported where things stand.
            raise HTTPException(
                status_code=409,
                detail="The team is still working on this request. Approve once they've finished their report.",
            )
        name = body.approved_by.strip()
        if body.decision == "approve" and not name:
            raise HTTPException(status_code=422, detail="approved_by (the approver's name) is required to approve")
        approval["status"] = "processing"

    deps = AgentDeps(run_id=approval["run_id"], agent="human", ticket_id=approval["ticket_id"])
    if body.decision == "deny":
        approval.update(status="denied", decided_by=name or None, decided_at=now())
        append_event(
            deps.run_id, "human", "approval_decision", approval_id=approval_id, tool=approval["tool"],
            args=approval["args"], decision="denied", approved_by=name or None,
        )
        return approval

    try:
        result = await call_as_human(mcp, approval["tool"], approval["args"], name, deps)
    except Exception as e:
        approval.update(status="pending")
        raise HTTPException(status_code=502, detail=f"Payment call failed: {type(e).__name__}: {e}")
    paid = isinstance(result, dict) and result.get("paid") is True
    approval.update(
        status="approved" if paid else "failed",
        decided_by=name,
        decided_at=now(),
        result=result,
    )
    append_event(
        deps.run_id, "human", "approval_result", approval_id=approval_id, tool=approval["tool"],
        paid=paid, result=result,
    )
    return approval


# ---------- Cash and reset ----------


@app.get("/api/cash")
async def checking_balance() -> dict:
    """Current checking balance from cash_accounts."""
    return await mcp_call("get_cash_balance", {"account": "checking"})


@app.post("/api/reset")
async def reset_database() -> dict:
    """Reset the working database to the original values for a fresh run. Clears pending approvals."""
    if (current := active_run()) is not None:
        raise HTTPException(status_code=409, detail=f"Run {current['run_id']} is still in progress")
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    cleared = len(approvals)
    approvals.clear()
    append_event("reset-" + uuid.uuid4().hex[:6], "harness", "db_reset", source=ORIGINAL_DB.name, target=WORKING_DB.name)
    return {"reset": True, "approvals_cleared": cleared, "cash": await mcp_call("get_cash_balance", {"account": "checking"})}


# ---------- Terminal runner ----------

BOARD_TASK = "Resolve every open ticket on the board."


async def _ask_in_terminal(message: str, deps: AgentDeps, tool: str, args: dict) -> str | None:
    """Terminal approver: show the payment and ask a person to type their name (Enter denies)."""
    print(f"\n{'=' * 70}\n{message}\n{'=' * 70}")
    name = await asyncio.to_thread(input, "Type your name to approve, or press Enter to deny: ")
    return name.strip() or None


async def run_board(reset: bool) -> None:
    """Work the whole board from the terminal, asking for payment approvals at the prompt."""
    run_id = uuid.uuid4().hex[:12]
    if reset:
        shutil.copyfile(ORIGINAL_DB, WORKING_DB)
        append_event(run_id, "harness", "db_reset", source=ORIGINAL_DB.name, target=WORKING_DB.name)
        print(f"Reset {WORKING_DB.name} from {ORIGINAL_DB.name}")
    append_event(run_id, "harness", "run_started", model=MODEL_NAME, db_reset=reset, task=BOARD_TASK)
    set_approver(_ask_in_terminal)
    try:
        async with mcp:
            append_event(run_id, "boss", "agent_started", task=BOARD_TASK)
            result = await team.boss.run(BOARD_TASK, deps=AgentDeps(run_id=run_id, agent="boss"), usage_limits=USAGE_LIMITS)
            append_event(run_id, "boss", "agent_finished", output=result.output)
    except Exception as e:
        append_event(run_id, "harness", "run_failed", error=f"{type(e).__name__}: {e}")
        raise
    usage = result.usage
    append_event(
        run_id, "harness", "run_finished",
        requests=usage.requests, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
    )
    print(f"\n{result.output}\n\n(run {run_id}: {usage.requests} model requests)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Campus Customs backend tools. Serve the API with: uvicorn main:app --reload --port 8000")
    parser.add_argument("--run-board", action="store_true", help="work every open ticket in the terminal")
    parser.add_argument("--no-reset", action="store_true", help="with --run-board: keep the current data")
    parser.add_argument("--verify-audit", action="store_true", help="check the audit trail's hash chain")
    opts = parser.parse_args()
    if opts.verify_audit:
        ok, msg = verify_audit()
        print(("OK: " if ok else "FAILED: ") + msg)
        sys.exit(0 if ok else 1)
    if opts.run_board:
        asyncio.run(run_board(reset=not opts.no_reset))
    else:
        parser.print_help()
