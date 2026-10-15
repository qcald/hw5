import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { AgentEvent, Approval, Cash, Run, Ticket } from './api'
import { Header } from './components/Header'
import { TicketDetail } from './components/TicketDetail'
import { TicketList } from './components/TicketList'
import { money } from './labels'

const BOARD_POLL_MS = 2500
const LIVE_POLL_MS = 1500

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [shopDate, setShopDate] = useState<string | null>(null)
  const [cash, setCash] = useState<Cash | null>(null)
  const [lastChange, setLastChange] = useState<number | null>(null)
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [allRuns, setAllRuns] = useState<Run[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [offline, setOffline] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  const [approverName, setApproverName] = useState(() => localStorage.getItem('cc-approver') ?? '')
  const [confirmReset, setConfirmReset] = useState(false)
  const prevBalance = useRef<number | null>(null)

  const busyTicketId = allRuns.find((r) => r.status === 'running')?.ticket_id ?? null

  const loadBoard = useCallback(async () => {
    try {
      const [t, c, a, ev] = await Promise.all([api.tickets(), api.cash(), api.approvals(), api.events({ limit: 1 })])
      setTickets(t.tickets)
      setShopDate(t.shop_date)
      setCash(c)
      if (prevBalance.current !== null && c.balance !== prevBalance.current) {
        setLastChange(c.balance - prevBalance.current)
      }
      prevBalance.current = c.balance
      setApprovals(a)
      setAllRuns(ev.runs)
      setSelectedId((id) => id ?? t.tickets.find((x) => x.state === 'open')?.id ?? t.tickets[0]?.id ?? null)
      setOffline(false)
    } catch {
      setOffline(true)
    }
  }, [])

  const loadTicket = useCallback(async () => {
    if (selectedId === null) return
    try {
      const ev = await api.events({ ticketId: selectedId })
      setEvents(ev.events)
      setRuns(ev.runs)
    } catch {
      setOffline(true)
    }
  }, [selectedId])

  useEffect(() => {
    loadBoard()
    const id = setInterval(loadBoard, BOARD_POLL_MS)
    return () => clearInterval(id)
  }, [loadBoard])

  useEffect(() => {
    setEvents([])
    setRuns([])
    loadTicket()
    const id = setInterval(loadTicket, busyTicketId === selectedId ? LIVE_POLL_MS : BOARD_POLL_MS * 2)
    return () => clearInterval(id)
  }, [loadTicket, busyTicketId, selectedId])

  const refresh = async () => {
    await Promise.all([loadBoard(), loadTicket()])
  }

  const startTeam = async () => {
    if (selectedId === null) return
    setNotice(null)
    try {
      await api.runTicket(selectedId)
    } catch (e) {
      setNotice({ tone: 'error', text: `Couldn't start the team: ${(e as Error).message}` })
    }
    await refresh()
  }

  const decide = async (approval: Approval, decision: 'approve' | 'deny') => {
    setNotice(null)
    try {
      const result = await api.decide(approval.approval_id, decision, approverName.trim())
      const r = result.result as { paid?: boolean; new_balance?: number; error?: string } | undefined
      if (decision === 'deny') setNotice({ tone: 'ok', text: 'Payment declined. Nothing was paid.' })
      else if (r?.paid) setNotice({ tone: 'ok', text: `Payment approved and sent. Checking is now ${money(Number(r.new_balance))}.` })
      else setNotice({ tone: 'error', text: `The payment didn't go through: ${r?.error ?? 'unknown reason'}` })
    } catch (e) {
      setNotice({ tone: 'error', text: (e as Error).message })
    }
    await refresh()
  }

  const reset = async () => {
    setConfirmReset(false)
    try {
      await api.reset()
      prevBalance.current = null
      setLastChange(null)
      setNotice({ tone: 'ok', text: 'Everything is back to how it started. The activity history is kept.' })
    } catch (e) {
      setNotice({ tone: 'error', text: `Couldn't start over: ${(e as Error).message}` })
    }
    await refresh()
  }

  const setName = (name: string) => {
    setApproverName(name)
    localStorage.setItem('cc-approver', name)
  }

  const selected = tickets.find((t) => t.id === selectedId) ?? null
  const approvalsByTicket: Record<number, number> = {}
  for (const a of approvals) {
    // Don't flag a payment while the team is still working; it's shown once they've reported.
    if (a.ticket_id !== null && a.ticket_id !== busyTicketId) approvalsByTicket[a.ticket_id] = (approvalsByTicket[a.ticket_id] ?? 0) + 1
  }

  return (
    <div className="app">
      <Header shopDate={shopDate} cash={cash} lastChange={lastChange} />

      {offline && (
        <div className="banner error page">Can't reach the shop system right now. Make sure the backend is running, then this page will catch up on its own.</div>
      )}
      {notice && (
        <div className={`banner page ${notice.tone === 'ok' ? 'done' : 'error'}`} role="status">
          {notice.text}
          <button className="link" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}

      <main className="layout">
        <TicketList
          tickets={tickets}
          selectedId={selectedId}
          runningTicketId={busyTicketId}
          approvalsByTicket={approvalsByTicket}
          onSelect={setSelectedId}
        />
        {selected ? (
          <TicketDetail
            key={selected.id}
            ticket={selected}
            events={events}
            runs={runs}
            busyTicketId={busyTicketId}
            approvals={approvals.filter((a) => a.ticket_id === selected.id)}
            approverName={approverName}
            onApproverName={setName}
            onStart={startTeam}
            onDecide={decide}
          />
        ) : (
          <div className="detail empty">{offline ? '' : 'Loading requests…'}</div>
        )}
      </main>

      <footer className="footer">
        {confirmReset ? (
          <span className="reset-confirm">
            Put every request, payment, and the bank balance back to how they started?
            <button className="btn danger small" onClick={reset} disabled={busyTicketId !== null}>
              Yes, start over
            </button>
            <button className="btn ghost small" onClick={() => setConfirmReset(false)}>
              Cancel
            </button>
          </span>
        ) : (
          <button className="link" onClick={() => setConfirmReset(true)} disabled={busyTicketId !== null}>
            Start over with fresh data
          </button>
        )}
        <span className="muted">Messages are only drafted, never sent. Payments always need a person's OK.</span>
      </footer>
    </div>
  )
}
