// Typed calls to the FastAPI backend (proxied from /api by Vite).

export type Ticket = {
  id: number
  type: string
  requester: string
  subject: string
  status: string
  state: 'open' | 'resolved'
  notes: string | null
  created_at: string
}

export type TicketsResponse = { shop_date: string; tickets: Ticket[] }

export type AgentEvent = {
  seq: number
  ts: string
  run_id: string
  agent: string
  event: string
  tool?: string
  args?: Record<string, unknown>
  result?: unknown
  to?: string
  ticket_id?: number
  approval_id?: string
  decision?: string
  approved_by?: string | null
  paid?: boolean
  said?: string
}

export type Run = {
  run_id: string
  ticket_id: number
  status: 'running' | 'finished' | 'failed' | 'interrupted'
  started_at: string
  finished_at?: string
  error?: string | null
}

export type EventsResponse = { events: AgentEvent[]; last_seq: number; runs: Run[] }

export type Approval = {
  approval_id: string
  status: string
  tool: string
  args: Record<string, unknown>
  message: string
  requested_by: string
  run_id: string
  ticket_id: number | null
  created_at: string
  result?: unknown
}

export type Cash = { name: string; balance: number; date: string }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      // not JSON; keep the status text
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  tickets: () => request<TicketsResponse>('/api/tickets'),
  cash: () => request<Cash>('/api/cash'),
  approvals: () => request<Approval[]>('/api/approvals'),
  events: (params: { ticketId?: number; limit?: number }) => {
    const q = new URLSearchParams({ limit: String(params.limit ?? 500) })
    if (params.ticketId !== undefined) q.set('ticket_id', String(params.ticketId))
    return request<EventsResponse>(`/api/events?${q}`)
  },
  runTicket: (ticketId: number) =>
    request<{ run_id: string; ticket_id: number; status: string }>(`/api/tickets/${ticketId}/run`, { method: 'POST' }),
  decide: (approvalId: string, decision: 'approve' | 'deny', approvedBy: string) =>
    request<Approval>(`/api/approvals/${approvalId}`, {
      method: 'POST',
      body: JSON.stringify({ decision, approved_by: approvedBy }),
    }),
  reset: () => request<{ reset: boolean; approvals_cleared: number; cash: Cash }>('/api/reset', { method: 'POST' }),
}
