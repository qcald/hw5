// Plain-language wording for agents, statuses, and tool calls, so the board reads like a person wrote it.

import type { AgentEvent, Approval, Ticket } from './api'

export type AgentInfo = { id: string; name: string; role: string; initials: string; color: string }

export const AGENTS: AgentInfo[] = [
  { id: 'boss', name: 'Boss', role: 'Runs the desk and hands out the work', initials: 'B', color: '#00356B' },
  { id: 'inventory', name: 'Inventory', role: 'Stock and suppliers', initials: 'In', color: '#286DC0' },
  { id: 'accounting', name: 'Accounting', role: 'Bills, cash, and payments', initials: 'Ac', color: '#2F6F5E' },
  { id: 'facilities', name: 'Facilities', role: 'The shop space and rent', initials: 'Fa', color: '#7A5C3E' },
  { id: 'customer_service', name: 'Customer Service', role: 'Replies to customers', initials: 'CS', color: '#6B4C8A' },
]

export const agentById = (id: string): AgentInfo | undefined => AGENTS.find((a) => a.id === id)

export const TICKET_KIND: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Discount request',
}

type StatusLook = { label: string; tone: 'new' | 'working' | 'attention' | 'waiting' | 'done' }

export function statusLook(status: string, running: boolean): StatusLook {
  if (running) return { label: 'Team is working', tone: 'working' }
  switch (status) {
    case 'open':
      return { label: 'New', tone: 'new' }
    case 'in_progress':
      return { label: 'In progress', tone: 'working' }
    case 'waiting_on_human':
      return { label: 'Needs your decision', tone: 'attention' }
    case 'waiting_on_vendor':
      return { label: 'Waiting on a delivery', tone: 'waiting' }
    case 'resolved':
      return { label: 'Resolved', tone: 'done' }
    default:
      return { label: status.replace(/_/g, ' '), tone: 'new' }
  }
}

export const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export const niceDate = (iso: string) => {
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso)
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
}

export const niceTime = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })

/** Split ticket notes into the original request, drafted messages, and status notes.
 *  Drafts and notes can span several lines: everything up to the next [DRAFT …] or [date status]
 *  marker belongs to the entry above it. */
export function parseNotes(notes: string | null) {
  const request: string[] = []
  const drafts: { date: string; to: string; text: string }[] = []
  const updates: { date: string; status: string; text: string }[] = []
  let current: { text: string } | null = null
  for (const raw of (notes ?? '').split('\n')) {
    const line = raw.trimEnd()
    const draft = line.match(/^\[DRAFT (\S+) to ([^\]]+)\]\s*(.*)$/)
    const update = line.match(/^\[(\d{4}-\d{2}-\d{2}) ([a-z_]+)\]\s*(.*)$/)
    if (draft) {
      const entry = { date: draft[1], to: draft[2], text: draft[3] }
      drafts.push(entry)
      current = entry
    } else if (update) {
      const entry = { date: update[1], status: update[2], text: update[3] }
      updates.push(entry)
      current = entry
    } else if (current) {
      current.text += `\n${line}`
    } else if (line.trim()) {
      request.push(line.trim())
    }
  }
  for (const entry of [...drafts, ...updates]) entry.text = entry.text.trim()
  return { request: request.join(' '), drafts, updates }
}

export function ticketHeadline(t: Ticket) {
  return t.subject
}

const asObj = (v: unknown): Record<string, unknown> | null =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null

const str = (v: unknown) => (v === undefined || v === null ? '' : String(v))

/** One short sentence describing a tool call, e.g. "Checked stock for CC-TEE-WHITE size S: 0 on hand". */
export function describeTool(e: AgentEvent): string {
  const a = e.args ?? {}
  const r = asObj(e.result)
  const err = r && typeof r.error === 'string' ? r.error : null
  switch (e.tool) {
    case 'get_shop_date':
      return "Checked today's date"
    case 'list_open_tickets':
    case 'list_tickets':
      return 'Looked over the open requests'
    case 'get_ticket':
      return `Read request #${str(a.ticket_id)}`
    case 'update_ticket':
      return `Marked request #${str(a.ticket_id)} as “${statusLook(str(a.status), false).label}”`
    case 'save_draft':
      return `Wrote a draft message to ${str(a.recipient)} (saved, not sent)`
    case 'check_stock': {
      const size = a.size ? ` size ${str(a.size)}` : ''
      const stock = Array.isArray(r?.stock) ? (r!.stock as { size: string; qty: number }[]) : null
      const found = stock ? `: ${stock.map((s) => `${s.qty} in ${s.size}`).join(', ')}` : ''
      return err ? `Tried to check stock for ${str(a.sku)}: ${err}` : `Checked stock for ${str(a.sku)}${size}${found}`
    }
    case 'list_vendors':
      return 'Looked up the suppliers and their delivery times'
    case 'get_restock_eta':
      if (err) return `Checked a restock: ${err}`
      if (r?.can_ship === false) return `${str(r.vendor)} can't ship ${str(a.qty)} more until its unpaid bill is settled`
      if (r?.arrival_date) return `${str(r.vendor)} could deliver ${str(a.qty)} more by ${niceDate(str(r.arrival_date))}`
      return 'Checked how long a restock would take'
    case 'quote_bulk_price':
      if (err) return `Tried to price an order: ${err}`
      return `Priced ${str(a.qty)} items at ${str(a.discount_pct ?? 0)}% off${r?.total !== undefined ? `: ${money(Number(r.total))} total` : ''}`
    case 'list_bills_due':
      return 'Reviewed the bills due and the bank balance'
    case 'get_lease':
      return 'Read the shop lease'
    case 'get_cash_balance':
      return 'Checked the bank balance'
    case 'list_payments':
      return 'Checked past payments'
    case 'pay_invoice':
    case 'pay_rent': {
      const what = e.tool === 'pay_rent' ? 'the rent' : `bill #${str(a.invoice_id)}`
      if (r?.status === 'pending_human_approval') return `Got a payment for ${what} ready. It's waiting for your OK`
      if (r?.paid === true) {
        const p = asObj(r.payment)
        return `Paid ${what}${p ? `: ${money(Number(p.amount))}, approved by ${str(p.approved_by)}` : ''}`
      }
      return `Couldn't pay ${what}: ${err ?? 'not approved'}`
    }
    default:
      return `Used ${str(e.tool)}`
  }
}

/** Pull the amount, payee, and balances out of the server's approval message. */
export function describeApproval(a: Approval) {
  const m = a.message.match(
    /pay \$([\d,.]+) from (\w+) \(balance \$([\d,.]+), \$(-?[\d,.]+) after\) for (.+?)\. Accept/,
  )
  if (!m) return { amount: null, account: null, before: null, after: null, what: a.message }
  const num = (s: string) => Number(s.replace(/,/g, ''))
  const what = m[5].charAt(0).toUpperCase() + m[5].slice(1)
  return { amount: num(m[1]), account: m[2], before: num(m[3]), after: num(m[4]), what }
}

/** First couple of sentences of a report, without markdown, for compact summaries. */
export function shortSummary(text: string, max = 260) {
  const plain = text
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#*_`>|]/g, '')
    .replace(/^\s*[-•]\s+/gm, '')
    .replace(/\s+/g, ' ')
    .trim()
  if (plain.length <= max) return plain
  const cut = plain.slice(0, max)
  const end = Math.max(cut.lastIndexOf('. '), cut.lastIndexOf('; '))
  return (end > 80 ? cut.slice(0, end + 1) : cut.trimEnd()) + ' …'
}
