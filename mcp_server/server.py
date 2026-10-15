"""Campus Customs MCP server.

Talks only to data/campus_customs_new.db (the original data/campus_customs.db is never touched).

Shop rules enforced here, so no client can skip them:
- "Today" is desk.date_today, never the system clock.
- A vendor with an open unpaid invoice will not ship new product.
- Every payment needs a human to approve it through an MCP input-required form. A client
  with no human to answer the form cannot pay.
- A payment that would make a cash balance negative is refused.
- Each payment is recorded in `payments` and updates `cash_accounts` and the invoice or lease.
- Nothing is sent to customers or vendors; drafts are saved on the ticket board.
"""

import json
import sqlite3
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

import mcp_types
from fastmcp import Context, FastMCP

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db"
TICKET_STATUSES = ("open", "in_progress", "waiting_on_vendor", "waiting_on_human", "resolved")

mcp = FastMCP("campus-customs")


def connect() -> sqlite3.Connection:
    # mode=rw: fail instead of silently creating an empty database.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=rw", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def shop_today(conn: sqlite3.Connection) -> date:
    """The shop's "today" comes from desk.date_today, never the system clock."""
    return date.fromisoformat(conn.execute("SELECT date_today FROM desk").fetchone()[0])


def open_invoices_for(conn: sqlite3.Connection, vendor_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, amount, due_date, description FROM invoices"
        " WHERE vendor_id = ? AND status != 'paid' ORDER BY due_date",
        (vendor_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


# ---------- Board: tickets and dates ----------


@mcp.tool
def get_shop_date() -> dict:
    """Return the shop's "today" (desk.date_today) and any desk notes. All due/overdue math uses this date."""
    with connect() as conn:
        return one(conn, "SELECT date_today, notes FROM desk")


@mcp.tool
def list_open_tickets() -> dict:
    """List every ticket that is not resolved, oldest first, along with the shop's date (desk.date_today)."""
    with connect() as conn:
        today = shop_today(conn)
        tickets = conn.execute(
            "SELECT * FROM tickets WHERE status != 'resolved' ORDER BY created_at"
        ).fetchall()
    return {"shop_date": today.isoformat(), "tickets": [dict(t) for t in tickets]}


@mcp.tool
def list_tickets() -> dict:
    """List every ticket (resolved or not) with its status, oldest first, along with the shop's date."""
    with connect() as conn:
        today = shop_today(conn)
        tickets = conn.execute("SELECT * FROM tickets ORDER BY created_at").fetchall()
    return {"shop_date": today.isoformat(), "tickets": [dict(t) for t in tickets]}


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Return one ticket with all its fields, including notes and any saved drafts."""
    with connect() as conn:
        ticket = one(conn, "SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    return ticket or {"error": f"No ticket {ticket_id}"}


@mcp.tool
def update_ticket(ticket_id: int, status: str, note: str) -> dict:
    """Set a ticket's status and append a dated note explaining why.
    status must be one of: open, in_progress, waiting_on_vendor, waiting_on_human, resolved."""
    if status not in TICKET_STATUSES:
        return {"error": f"status must be one of {list(TICKET_STATUSES)}"}
    if not note.strip():
        return {"error": "note is required"}
    with connect() as conn:
        ticket = one(conn, "SELECT notes FROM tickets WHERE id = ?", (ticket_id,))
        if not ticket:
            return {"error": f"No ticket {ticket_id}"}
        entry = f"[{shop_today(conn).isoformat()} {status}] {note.strip()}"
        notes = f"{ticket['notes']}\n{entry}" if ticket["notes"] else entry
        conn.execute(
            "UPDATE tickets SET status = ?, notes = ? WHERE id = ?", (status, notes, ticket_id)
        )
        return one(conn, "SELECT id, status, notes FROM tickets WHERE id = ?", (ticket_id,))


@mcp.tool
def save_draft(ticket_id: int, recipient: str, message: str) -> dict:
    """Save a draft message (to a customer, vendor, or landlord) in the ticket's notes.
    Drafts stay on the board; nothing is ever emailed, called, or sent."""
    if not recipient.strip() or not message.strip():
        return {"error": "recipient and message are required"}
    with connect() as conn:
        ticket = one(conn, "SELECT notes FROM tickets WHERE id = ?", (ticket_id,))
        if not ticket:
            return {"error": f"No ticket {ticket_id}"}
        draft = f"[DRAFT {shop_today(conn).isoformat()} to {recipient.strip()}] {message.strip()}"
        notes = f"{ticket['notes']}\n{draft}" if ticket["notes"] else draft
        conn.execute("UPDATE tickets SET notes = ? WHERE id = ?", (notes, ticket_id))
    return {"ticket_id": ticket_id, "saved_draft": draft, "sent": False}


# ---------- Inventory and vendors ----------


@mcp.tool
def check_stock(sku: str, size: str | None = None) -> dict:
    """Show how many units of a SKU are on hand, per size, with location, unit cost, and list price.
    Pass a size to check just that size."""
    with connect() as conn:
        sql, params = "SELECT size, qty, location FROM inventory WHERE sku = ?", [sku]
        if size:
            sql += " AND size = ?"
            params.append(size)
        stock = conn.execute(sql, params).fetchall()
        item = conn.execute("SELECT name FROM inventory WHERE sku = ?", (sku,)).fetchone()
        price = conn.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
    if not item:
        return {"error": f"No inventory for SKU {sku}"}
    return {
        "sku": sku,
        "name": item["name"],
        "unit_cost": price["unit_cost"] if price else None,
        "list_price": price["list_price"] if price else None,
        "stock": [dict(s) for s in stock],
    }


@mcp.tool
def list_vendors() -> list[dict]:
    """List vendors with their specialty, lead_days, any open unpaid invoices, and can_ship
    (false while an open unpaid invoice exists, because the vendor will not ship until it is paid)."""
    with connect() as conn:
        vendors = [dict(v) for v in conn.execute("SELECT * FROM vendors ORDER BY id").fetchall()]
        for v in vendors:
            v["open_invoices"] = open_invoices_for(conn, v["id"])
            v["can_ship"] = not v["open_invoices"]
    return vendors


@mcp.tool
def get_restock_eta(sku: str, size: str, qty: int, vendor_id: int) -> dict:
    """Check a restock from a vendor without ordering anything. Returns current stock, estimated cost
    (pricing.unit_cost x qty), and either the arrival date (desk.date_today + vendor lead_days)
    or the open invoices blocking the vendor from shipping."""
    if qty <= 0:
        return {"error": "qty must be positive"}
    with connect() as conn:
        vendor = one(conn, "SELECT * FROM vendors WHERE id = ?", (vendor_id,))
        if not vendor:
            return {"error": f"No vendor {vendor_id}"}
        stock = one(conn, "SELECT qty FROM inventory WHERE sku = ? AND size = ?", (sku, size))
        if not stock:
            return {"error": f"No inventory row for {sku} size {size}"}
        price = one(conn, "SELECT unit_cost FROM pricing WHERE sku = ?", (sku,))
        today = shop_today(conn)
        blocking = open_invoices_for(conn, vendor_id)
    result = {
        "sku": sku,
        "size": size,
        "qty": qty,
        "current_stock": stock["qty"],
        "vendor_id": vendor_id,
        "vendor": vendor["name"],
        "specialty": vendor["specialty"],
        "lead_days": vendor["lead_days"],
        "estimated_cost": round(price["unit_cost"] * qty, 2) if price else None,
        "can_ship": not blocking,
    }
    if blocking:
        result["blocked_by_invoices"] = blocking
    else:
        result["arrival_date"] = (today + timedelta(days=vendor["lead_days"])).isoformat()
    return result


@mcp.tool
def quote_bulk_price(sku: str, qty: int, discount_pct: float = 0.0) -> dict:
    """Price qty units of a SKU at an optional percent discount off list price. Returns unit price, total,
    margin per unit, and margin percent, and flags pricing below cost. Changes nothing."""
    if qty <= 0 or not 0 <= discount_pct < 100:
        return {"error": "qty must be positive and discount_pct must be at least 0 and below 100"}
    with connect() as conn:
        price = one(conn, "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,))
    if not price:
        return {"error": f"No pricing for SKU {sku}"}
    unit_price = round(price["list_price"] * (1 - discount_pct / 100), 2)
    margin = round(unit_price - price["unit_cost"], 2)
    return {
        "sku": sku,
        "qty": qty,
        "list_price": price["list_price"],
        "unit_cost": price["unit_cost"],
        "discount_pct": discount_pct,
        "unit_price": unit_price,
        "total": round(unit_price * qty, 2),
        "margin_per_unit": margin,
        "margin_pct": round(100 * margin / unit_price, 1) if unit_price else None,
        "below_cost": margin < 0,
    }


# ---------- Money: bills, leases, payments ----------


@mcp.tool
def list_bills_due() -> dict:
    """List unpaid vendor invoices and lease rent, each with days until due and an overdue flag
    measured from desk.date_today, plus the current cash balance. Read-only; pays nothing."""
    with connect() as conn:
        today = shop_today(conn)
        invoices = conn.execute(
            "SELECT i.id AS invoice_id, v.id AS vendor_id, v.name AS vendor, i.amount,"
            " i.due_date, i.status, i.description"
            " FROM invoices i JOIN vendors v ON v.id = i.vendor_id"
            " WHERE i.status != 'paid' ORDER BY i.due_date"
        ).fetchall()
        leases = conn.execute(
            "SELECT id AS lease_id, space_name, landlord, monthly_rent AS amount,"
            " next_due AS due_date FROM leases ORDER BY next_due"
        ).fetchall()
        cash = conn.execute("SELECT name, balance FROM cash_accounts").fetchall()

    def with_timing(row: sqlite3.Row) -> dict:
        bill = dict(row)
        days = (date.fromisoformat(bill["due_date"]) - today).days
        bill["days_until_due"] = days
        bill["overdue"] = days < 0
        return bill

    return {
        "shop_date": today.isoformat(),
        "cash": [dict(c) for c in cash],
        "unpaid_invoices": [with_timing(i) for i in invoices],
        "rent": [with_timing(l) for l in leases],
    }


@mcp.tool
def get_lease(lease_id: int) -> dict:
    """Return one lease (space, landlord, monthly rent, next due date, notes) with days until due
    measured from desk.date_today."""
    with connect() as conn:
        lease = one(conn, "SELECT * FROM leases WHERE id = ?", (lease_id,))
        if not lease:
            return {"error": f"No lease {lease_id}"}
        today = shop_today(conn)
    days = (date.fromisoformat(lease["next_due"]) - today).days
    return {**lease, "days_until_due": days, "overdue": days < 0}


@mcp.tool
def get_cash_balance(account: str = "checking") -> dict:
    """Return one cash account's current balance and the date it was last updated."""
    with connect() as conn:
        acct = one(conn, "SELECT * FROM cash_accounts WHERE name = ?", (account,))
    return acct or {"error": f"No cash account '{account}'"}


@mcp.tool
def list_payments() -> list[dict]:
    """Return every payment made so far (the payment ledger), including who approved each one."""
    with connect() as conn:
        return [dict(p) for p in conn.execute("SELECT * FROM payments ORDER BY id").fetchall()]


def payment_target(conn: sqlite3.Connection, kind: str, ref_id: int, account: str) -> dict:
    """Look up what a payment would cover. Returns {'error': ...} if it can't be paid."""
    if kind == "invoice":
        inv = one(conn, "SELECT * FROM invoices WHERE id = ?", (ref_id,))
        if not inv:
            return {"error": f"No invoice {ref_id}"}
        if inv["status"] == "paid":
            return {"error": f"Invoice {ref_id} is already paid"}
        vendor = one(conn, "SELECT name FROM vendors WHERE id = ?", (inv["vendor_id"],))
        amount = inv["amount"]
        what = f"invoice {ref_id} to {vendor['name']} ({inv['description']}), due {inv['due_date']}"
    else:
        lease = one(conn, "SELECT * FROM leases WHERE id = ?", (ref_id,))
        if not lease:
            return {"error": f"No lease {ref_id}"}
        amount = lease["monthly_rent"]
        what = f"rent for {lease['space_name']} to {lease['landlord']}, due {lease['next_due']}"
    acct = one(conn, "SELECT * FROM cash_accounts WHERE name = ?", (account,))
    if not acct:
        return {"error": f"No cash account '{account}'"}
    if acct["balance"] < amount:
        return {
            "error": f"Insufficient cash: {account} has ${acct['balance']:.2f}, "
            f"payment needs ${amount:.2f}. Payment refused; balances can't go negative."
        }
    return {"amount": amount, "what": what, "balance": acct["balance"]}


def make_payment(
    kind: str, ref_id: int, account: str, ctx: Context
) -> dict | mcp_types.InputRequiredResult:
    with connect() as conn:
        target = payment_target(conn, kind, ref_id, account)
    if "error" in target:
        return {"paid": False, **target}

    # Round 1: ask a human. The client shows the form and retries this call with the answer.
    state = {"kind": kind, "ref_id": ref_id, "account": account, "amount": target["amount"]}
    responses = ctx.input_responses
    if not responses:
        return mcp_types.InputRequiredResult(
            input_requests={
                "approval": mcp_types.ElicitRequest(
                    params=mcp_types.ElicitRequestFormParams(
                        message=(
                            f"APPROVAL NEEDED: pay ${target['amount']:.2f} from {account} "
                            f"(balance ${target['balance']:.2f}, "
                            f"${target['balance'] - target['amount']:.2f} after) for {target['what']}. "
                            "Accept and enter your name to approve, or decline to refuse."
                        ),
                        requested_schema={
                            "type": "object",
                            "properties": {
                                "approved_by": {"type": "string", "title": "Approver name"}
                            },
                            "required": ["approved_by"],
                        },
                    )
                )
            },
            # Sealed by FastMCP, so the amount the human saw can't be swapped on the retry.
            request_state=json.dumps(state),
        )

    # Round 2: check the human's answer.
    if json.loads(ctx.request_state or "{}") != state:
        return {"paid": False, "error": "Payment changed since approval was requested; ask again."}
    answer = responses.get("approval")
    content = getattr(answer, "content", None) or {}
    approved_by = str(content.get("approved_by") or "").strip()
    if not answer or answer.action != "accept" or not approved_by:
        return {"paid": False, "error": "Payment not approved by a human. Nothing was paid."}

    # Apply atomically, re-checking cash in case another payment landed meanwhile.
    amount = target["amount"]
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        recheck = payment_target(conn, kind, ref_id, account)
        if "error" in recheck:
            return {"paid": False, **recheck}
        today = shop_today(conn).isoformat()
        if kind == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
        else:
            next_due = one(conn, "SELECT next_due FROM leases WHERE id = ?", (ref_id,))["next_due"]
            next_due = add_months(date.fromisoformat(next_due), 1).isoformat()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (next_due, ref_id))
        conn.execute(
            "UPDATE cash_accounts SET balance = balance - ?, date = ? WHERE name = ?",
            (amount, today, account),
        )
        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (kind, ref_id, amount, account, today, approved_by),
        )
        payment = one(conn, "SELECT * FROM payments WHERE id = ?", (cur.lastrowid,))
        balance = one(conn, "SELECT balance FROM cash_accounts WHERE name = ?", (account,))
    return {"paid": True, "payment": payment, "new_balance": balance["balance"]}


@mcp.tool
def pay_invoice(
    invoice_id: int, ctx: Context, account: str = "checking"
) -> dict | mcp_types.InputRequiredResult:
    """Pay a vendor invoice in full from a cash account. The amount comes from the invoice.
    A human must approve: they are shown the amount and payee and must accept and enter their name.
    Refused if they decline, if the invoice is already paid, or if cash would go negative.
    On success the invoice is marked paid, cash is reduced, and the payment is logged."""
    return make_payment("invoice", invoice_id, account, ctx)


@mcp.tool
def pay_rent(
    lease_id: int, ctx: Context, account: str = "checking"
) -> dict | mcp_types.InputRequiredResult:
    """Pay one month of rent for a lease from a cash account. The amount is the lease's monthly_rent.
    A human must approve: they are shown the amount and landlord and must accept and enter their name.
    Refused if they decline or if cash would go negative.
    On success the lease's next_due moves forward one month, cash is reduced, and the payment is logged."""
    return make_payment("rent", lease_id, account, ctx)


if __name__ == "__main__":
    mcp.run(show_banner=False)
