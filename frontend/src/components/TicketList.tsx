import type { Ticket } from '../api'
import { TICKET_KIND, parseNotes } from '../labels'
import { Status } from './Status'
import { TicketIcon } from './TicketIcon'

type Props = {
  tickets: Ticket[]
  selectedId: number | null
  runningTicketId: number | null
  approvalsByTicket: Record<number, number>
  onSelect: (id: number) => void
}

export function TicketList({ tickets, selectedId, runningTicketId, approvalsByTicket, onSelect }: Props) {
  const open = tickets.filter((t) => t.state === 'open').length
  return (
    <nav className="requests" aria-label="Requests">
      <div className="requests-head">
        <h2 className="eyebrow">Requests</h2>
        <span className="requests-count">
          {open} open · {tickets.length - open} resolved
        </span>
      </div>
      <div className="requests-list">
        {tickets.map((t) => {
          const needsOk = approvalsByTicket[t.id] ?? 0
          return (
            <button
              key={t.id}
              className={`request ${selectedId === t.id ? 'selected' : ''} ${t.state === 'resolved' ? 'is-resolved' : ''}`}
              onClick={() => onSelect(t.id)}
              aria-current={selectedId === t.id}
            >
              <TicketIcon type={t.type} />
              <span className="request-body">
                <span className="request-kind">
                  {TICKET_KIND[t.type] ?? t.type} <span className="request-id">#{t.id}</span>
                </span>
                <span className="request-title">{t.subject}</span>
                <span className="request-text">{parseNotes(t.notes).request || `From ${t.requester}`}</span>
                <span className="request-status">
                  <Status status={t.status} running={runningTicketId === t.id} />
                  {needsOk > 0 && <span className="flag">Approval waiting</span>}
                </span>
              </span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
