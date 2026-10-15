"""The Campus Customs agent layer: the model, the MCP connection, the audit trail, and the agent team.

- Model: every agent uses gpt-6-luna through Portkey (MODEL_NAME is the only model named anywhere).
- MCP: all shop facts reach the agents and the API through the campus-customs MCP server, launched
  exactly as configured in hw5/.mcp.json. Nothing in backend/ reads the database.
- Audit: every agent run, hand-off, tool call, and approval is appended to output/audit_trail.json
  (hash-chained, never rewritten). Check it with:  python backend/main.py --verify-audit
- Team: a Boss agent that delegates to four specialists, each limited to its own MCP tools.
  Prompts live in backend/prompts/<agent>.md.

Payment approvals: the MCP server's pay tools return an approval form instead of paying.
- During an agent run, the configured approver decides. The API (main.py) queues the payment for the
  dashboard, so the agent only prepares it and is told it is pending. The terminal runner asks a
  person right away.
- `call_as_human` is used by the dashboard's approve route after a person clicks approve. It is the
  only path that answers the approval form with "approved", so it is what actually changes cash.
"""

import fcntl
import hashlib
import json
import os
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult
from fastmcp.client.transports import StdioTransport
from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.mcp import CallToolFunc, MCPToolset
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

# =====================================================================================
# Config
# =====================================================================================

BACKEND_DIR = Path(__file__).resolve().parent
HW_DIR = BACKEND_DIR.parent
MCP_CONFIG = HW_DIR / ".mcp.json"
MCP_SERVER_NAME = "campus-customs"
PROMPTS_DIR = BACKEND_DIR / "prompts"
AUDIT_PATH = HW_DIR / "output" / "audit_trail.json"
ORIGINAL_DB = HW_DIR / "data" / "campus_customs.db"
WORKING_DB = HW_DIR / "data" / "campus_customs_new.db"

# The assignment allows only this model, for every agent. Don't add another.
MODEL_NAME = "gpt-6-luna"

load_dotenv(HW_DIR / ".env")
load_dotenv(HW_DIR.parent / ".env")
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")


def build_model() -> OpenAIResponsesModel:
    api_key = os.environ.get("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set (put it in .env)")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.portkey.ai/v1",
        default_headers={"x-portkey-api-key": api_key},
    )
    # The Responses API: gpt-6-luna doesn't allow tool calls with reasoning on /v1/chat/completions.
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


# =====================================================================================
# Audit trail (append-only, hash-chained JSON array, one entry per line)
# =====================================================================================

GENESIS_HASH = "0" * 64
PREVIEW_CHARS = 1500  # long tool results are truncated to keep entries readable

_audit_lock = threading.Lock()


def _preview(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) <= PREVIEW_CHARS:
        return value
    return text[:PREVIEW_CHARS] + f"... [truncated {len(text) - PREVIEW_CHARS} chars]"


def _hash(prev_hash: str, entry: dict) -> str:
    body = json.dumps(entry, sort_keys=True, default=str)
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


def _last_entry(data: bytes) -> dict | None:
    for line in reversed(data.splitlines()):
        line = line.strip().rstrip(b",")
        if line.startswith(b"{"):
            return json.loads(line)
    return None


def append_event(run_id: str, agent: str, event: str, **fields: Any) -> None:
    """Append one event to the audit trail. Never overwrites existing entries: it removes the
    closing `]`, writes the new entry, and puts the `]` back. Each entry stores the hash of the one
    before it, so editing, reordering, or deleting history breaks the chain."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.touch(exist_ok=True)
    with _audit_lock, open(AUDIT_PATH, "r+b") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            data = f.read()
            stripped = data.rstrip()
            if stripped and not stripped.endswith(b"]"):
                raise RuntimeError(f"{AUDIT_PATH} is not a JSON array; refusing to write")
            last = _last_entry(data) if stripped else None

            entry = {
                "seq": (last["seq"] + 1) if last else 1,
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "run_id": run_id,
                "agent": agent,
                "event": event,
                **{k: _preview(v) for k, v in fields.items()},
            }
            prev_hash = last["hash"] if last else GENESIS_HASH
            entry["prev_hash"] = prev_hash
            entry["hash"] = _hash(prev_hash, entry)
            line = json.dumps(entry, default=str).encode()

            if last is None:
                if stripped not in (b"", b"[]", b"[\n]"):
                    raise RuntimeError(f"{AUDIT_PATH} has unexpected content; refusing to write")
                f.seek(0)
                f.truncate()
                f.write(b"[\n" + line + b"\n]\n")
            else:
                # Cut only the closing "]" (and whitespace before it), then add the new line.
                end_of_last_entry = len(stripped[:-1].rstrip())
                f.seek(end_of_last_entry)
                f.truncate()
                f.write(b",\n" + line + b"\n]\n")
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def verify_audit() -> tuple[bool, str]:
    """Check that the audit file parses and the hash chain is unbroken."""
    if not AUDIT_PATH.exists():
        return True, "no audit trail yet"
    entries = json.loads(AUDIT_PATH.read_text() or "[]")
    prev = GENESIS_HASH
    for i, e in enumerate(entries, start=1):
        claimed = e.get("hash")
        body = {k: v for k, v in e.items() if k != "hash"}
        if e.get("seq") != i or e.get("prev_hash") != prev or _hash(prev, body) != claimed:
            return False, f"chain broken at entry {i}"
        prev = claimed
    return True, f"{len(entries)} entries, chain intact"


# =====================================================================================
# MCP connection, tool-call auditing, and payment approvals
# =====================================================================================


@dataclass
class AgentDeps:
    """Passed to every agent run so tool calls are audited under the right agent."""

    run_id: str
    agent: str
    ticket_id: int | None = None


@dataclass
class PendingApproval:
    """An approver's answer meaning "queued for a human later": decline now, pay nothing."""

    approval_id: str


@dataclass
class _Call:
    deps: AgentDeps
    tool: str
    args: dict[str, Any]
    pending_id: str | None = None
    human_approver: str | None = None  # set only by call_as_human


# An approver receives the server's approval message and the call that triggered it, and returns
# the approver's name (pay now), None (deny), or PendingApproval (queue it for the dashboard).
Approver = Callable[[str, AgentDeps, str, dict[str, Any]], Awaitable["str | PendingApproval | None"]]

_current_call: ContextVar[_Call | None] = ContextVar("current_call", default=None)


async def _deny_all(message: str, deps: AgentDeps, tool: str, args: dict[str, Any]) -> None:
    return None


_approver: Approver = _deny_all


def set_approver(approver: Approver) -> None:
    global _approver
    _approver = approver


async def _approval_handler(message: str, response_type: Any, params: Any, context: Any) -> Any:
    call = _current_call.get() or _Call(AgentDeps("unknown", "unknown"), "unknown", {})
    deps = call.deps

    if call.human_approver:
        # The dashboard approve route: a person already clicked approve for this exact call.
        append_event(
            deps.run_id, deps.agent, "approval_decision", tool=call.tool, args=call.args,
            decision="approved", approved_by=call.human_approver, message=message,
        )
        return {"approved_by": call.human_approver}

    append_event(deps.run_id, deps.agent, "approval_requested", tool=call.tool, args=call.args, message=message)
    outcome = await _approver(message, deps, call.tool, call.args)
    if isinstance(outcome, PendingApproval):
        call.pending_id = outcome.approval_id
        append_event(
            deps.run_id, deps.agent, "approval_queued", tool=call.tool, args=call.args,
            approval_id=outcome.approval_id,
        )
        return ElicitResult(action="decline")

    name = (outcome or "").strip()
    append_event(
        deps.run_id, deps.agent, "approval_decision", tool=call.tool, args=call.args,
        decision="approved" if name else "denied", approved_by=name or None,
    )
    return {"approved_by": name} if name else ElicitResult(action="decline")


async def _audited_call(
    ctx: RunContext[AgentDeps], call_tool: CallToolFunc, name: str, args: dict[str, Any]
) -> Any:
    deps = ctx.deps
    call = _Call(deps, name, args)
    token = _current_call.set(call)
    start = time.monotonic()
    try:
        result = await call_tool(name, args)
    except Exception as e:
        append_event(
            deps.run_id, deps.agent, "tool_error", tool=name, args=args,
            error=f"{type(e).__name__}: {e}", duration_ms=round((time.monotonic() - start) * 1000),
        )
        raise
    finally:
        _current_call.reset(token)
    if call.pending_id:
        # Tell the agent the truth: prepared and queued, not paid.
        result = {
            "paid": False,
            "status": "pending_human_approval",
            "approval_id": call.pending_id,
            "message": "Payment prepared and queued for a human to approve on the dashboard. Nothing has been paid yet.",
        }
    append_event(
        deps.run_id, deps.agent, "tool_call", tool=name, args=args,
        result=result, duration_ms=round((time.monotonic() - start) * 1000),
    )
    return result


async def call_as_human(
    mcp: MCPToolset, tool: str, args: dict[str, Any], approved_by: str, deps: AgentDeps
) -> Any:
    """Call a payment tool on behalf of a person who clicked approve. Answers the approval form with their name."""
    call = _Call(deps, tool, args, human_approver=approved_by)
    token = _current_call.set(call)
    try:
        result = await mcp.direct_call_tool(tool, args)
    finally:
        _current_call.reset(token)
    append_event(deps.run_id, deps.agent, "tool_call", tool=tool, args=args, result=result)
    return result


def build_mcp_toolset() -> MCPToolset:
    """Connect to the server defined in .mcp.json (same command and args Claude Code uses)."""
    server = json.loads(MCP_CONFIG.read_text())["mcpServers"][MCP_SERVER_NAME]
    transport = StdioTransport(command=server["command"], args=server.get("args", []), env=server.get("env"))
    client = Client(transport, elicitation_handler=_approval_handler)
    return MCPToolset(client, process_tool_call=_audited_call)


# =====================================================================================
# The agent team
# =====================================================================================

SPECIALISTS = ("inventory", "accounting", "facilities", "customer_service")

# Which campus-customs MCP tools each agent may call.
AGENT_TOOLS: dict[str, set[str]] = {
    "boss": {"get_shop_date", "list_open_tickets", "get_ticket", "update_ticket"},
    "inventory": {
        "get_shop_date", "get_ticket", "check_stock", "list_vendors", "get_restock_eta", "save_draft",
    },
    "accounting": {
        "get_shop_date", "get_ticket", "list_bills_due", "list_payments", "quote_bulk_price",
        "pay_invoice", "pay_rent",
    },
    "facilities": {"get_shop_date", "get_ticket", "get_lease", "list_bills_due", "save_draft"},
    "customer_service": {
        "get_shop_date", "get_ticket", "check_stock", "quote_bulk_price", "save_draft",
    },
}

# Caps model requests across the whole run (boss plus every delegation) to limit token burn.
USAGE_LIMITS = UsageLimits(request_limit=80)


def load_prompts() -> dict[str, str]:
    """Read backend/prompts/<agent>.md for the boss and each specialist."""
    prompts = {}
    for name in ("boss", *SPECIALISTS):
        path = PROMPTS_DIR / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Missing prompt file: {path}")
        prompts[name] = path.read_text().strip()
    return prompts


@dataclass
class Team:
    boss: Agent[AgentDeps, str]
    specialists: dict[str, Agent[AgentDeps, str]]


def build_team(mcp: MCPToolset) -> Team:
    model = build_model()
    prompts = load_prompts()

    def make_agent(name: str) -> Agent[AgentDeps, str]:
        allowed = AGENT_TOOLS[name]
        tools = mcp.filtered(lambda ctx, tool_def: tool_def.name in allowed)
        return Agent(
            model,
            name=name,
            deps_type=AgentDeps,
            instructions=prompts[name],
            toolsets=[tools],
        )

    specialists = {name: make_agent(name) for name in SPECIALISTS}
    boss = make_agent("boss")

    async def delegate(ctx: RunContext[AgentDeps], specialist: str, task: str) -> str:
        run_id = ctx.deps.run_id
        append_event(run_id, "boss", "delegation", to=specialist, task=task)
        append_event(run_id, specialist, "agent_started", task=task)
        try:
            result = await specialists[specialist].run(
                task,
                deps=AgentDeps(run_id=run_id, agent=specialist, ticket_id=ctx.deps.ticket_id),
                usage=ctx.usage,
                usage_limits=USAGE_LIMITS,
            )
        except Exception as e:
            append_event(run_id, specialist, "agent_error", error=f"{type(e).__name__}: {e}")
            return f"The {specialist} agent failed: {type(e).__name__}: {e}"
        append_event(run_id, specialist, "agent_finished", output=result.output)
        return result.output

    @boss.tool
    async def ask_inventory(ctx: RunContext[AgentDeps], task: str) -> str:
        """Send a task to the inventory agent (stock, vendors, lead times, restock ETAs, draft vendor orders)."""
        return await delegate(ctx, "inventory", task)

    @boss.tool
    async def ask_accounting(ctx: RunContext[AgentDeps], task: str) -> str:
        """Send a task to the accounting agent (bills due, cash planning, margins, and human-approved payments)."""
        return await delegate(ctx, "accounting", task)

    @boss.tool
    async def ask_facilities(ctx: RunContext[AgentDeps], task: str) -> str:
        """Send a task to the facilities agent (leases, rent notices, draft replies to the landlord)."""
        return await delegate(ctx, "facilities", task)

    @boss.tool
    async def ask_customer_service(ctx: RunContext[AgentDeps], task: str) -> str:
        """Send a task to the customer service agent (draft replies to customers and requesters)."""
        return await delegate(ctx, "customer_service", task)

    return Team(boss=boss, specialists=specialists)
