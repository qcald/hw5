import { useState } from 'react'
import type { AgentEvent, Approval, Run, Ticket } from '../api'
import { TICKET_KIND, niceDate, niceTime, parseNotes, shortSummary, statusLook } from '../labels'
import { Activity } from './Activity'
import { ApprovalCard } from './ApprovalCard'
import { Draft } from './Draft'
import { Summary } from './Summary'
import { Team } from './Team'
import { Status } from './Status'
import { TicketIcon } from './TicketIcon'

type Props = {
  ticket: Ticket
  events: AgentEvent[]
  runs: Run[]
  busyTicketId: number | null
  approvals: Approval[]
  approverName: string
  onApproverName: (name: string) => void
  onStart: () => Promise<void>
  onDecide: (approval: Approval, decision: 'approve' | 'deny') => Promise<void>
}

export function TicketDetail(props: Props) {
  const { ticket, events, runs, busyTicketId, approvals } = props
  const [starting, setStarting] = useState(false)
  const [tab, setTab] = useState<'live' | 'summary'>('live')

  const running = busyTicketId === ticket.id
  const lastRun = runs[runs.length - 1]
  const notes = parseNotes(ticket.notes)
  const lastUpdate = notes.updates[notes.updates.length - 1]
  const look = statusLook(ticket.status, running)
  const resolved = ticket.state === 'resolved'
  // The Boss's wrap-up for the latest run, used if it didn't leave a status note on the ticket.
  const bossReport = events.filter((e) => e.run_id === lastRun?.run_id && e.agent === 'boss' && e.event === 'agent_finished').pop()?.said
  const standsText = lastUpdate?.text ?? (bossReport ? shortSummary(bossReport, 420) : null)
  // Approvals wait until the team has finished and reported, so you read where things stand first.
  const showApprovals = !running && !starting

  const start = async () => {
    setStarting(true)
    setTab('live')
    try {
      await props.onStart()
    } finally {
      setStarting(false)
    }
  }

  let action: { label: string; disabled: boolean; hint?: string } | null
  if (resolved) action = null
  else if (running || starting) action = { label: 'The team is working…', disabled: true }
  else if (busyTicketId !== null)
    action = { label: 'Start the team', disabled: true, hint: `The team is busy with request #${busyTicketId}. You can start this one when they're done.` }
  else if (approvals.length && showApprovals) action = null
  else if (!runs.length) action = { label: 'Start the team on this request', disabled: false }
  else action = { label: 'Ask the team to pick it back up', disabled: false, hint: 'They will see everything that has happened so far, including any payments you approved.' }

  return (
    <article className="detail">
      <header className="detail-head">
        <div className="detail-meta">
          <TicketIcon type={ticket.type} />
          <span>
            {TICKET_KIND[ticket.type] ?? ticket.type} <span className="request-id">#{ticket.id}</span>
          </span>
          <span className="sep">·</span>
          <span>{ticket.requester}</span>
          <span className="sep">·</span>
          <span>
            {niceDate(ticket.created_at)}, {niceTime(ticket.created_at)}
          </span>
        </div>
        <div className="detail-title-row">
          <h1>{ticket.subject}</h1>
          <Status status={ticket.status} running={running} large />
        </div>
        {notes.request && <p className="detail-request">{notes.request}</p>}
      </header>

      {(resolved || (!running && lastRun && lastRun.status !== 'running' && standsText)) && (
        <section className={`callout ${resolved ? 'done' : look.tone}`}>
          <div className="eyebrow">{resolved ? 'Resolved' : 'Where it stands'}</div>
          <p>{standsText ?? 'The team finished this request.'}</p>
        </section>
      )}
      {lastRun?.status === 'failed' && !running && <RunError error={lastRun.error ?? ''} />}

      {running && approvals.length > 0 && (
        <p className="quiet-note">
          The team has prepared {approvals.length === 1 ? 'a payment' : `${approvals.length} payments`}. You'll be asked to
          approve once they finish and report where things stand.
        </p>
      )}
      {showApprovals &&
        approvals.map((a) => (
          <ApprovalCard
            key={a.approval_id}
            approval={a}
            approverName={props.approverName}
            onApproverName={props.onApproverName}
            onDecide={props.onDecide}
          />
        ))}

      {action && (
        <div className="start">
          <button className="btn primary large" disabled={action.disabled} onClick={start}>
            {(running || starting) && <span className="spinner" aria-hidden />}
            {action.label}
          </button>
          {action.hint && <span className="start-hint">{action.hint}</span>}
        </div>
      )}

      <section className="block">
        <h2 className="eyebrow">The team</h2>
        <Team events={events} running={running} />
      </section>

      {notes.drafts.length > 0 && (
        <section className="block">
          <div className="block-head">
            <h2 className="eyebrow">Drafted messages</h2>
            <span className="block-note">Saved here only. Nothing was emailed or sent.</span>
          </div>
          <div className="drafts">
            {notes.drafts.map((d, i) => (
              <Draft key={i} to={d.to} date={d.date} text={d.text} />
            ))}
          </div>
        </section>
      )}

      <section className="block">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === 'live'} className={tab === 'live' ? 'active' : ''} onClick={() => setTab('live')}>
            Step by step
          </button>
          <button role="tab" aria-selected={tab === 'summary'} className={tab === 'summary' ? 'active' : ''} onClick={() => setTab('summary')}>
            What each person did
          </button>
        </div>
        <div className="tab-panel">{tab === 'live' ? <Activity events={events} /> : <Summary events={events} />}</div>
      </section>
    </article>
  )
}

function RunError({ error }: { error: string }) {
  const [open, setOpen] = useState(false)
  return (
    <section className="callout error">
      <div className="eyebrow">The last run didn't finish</div>
      <p>
        Something went wrong partway through, so nothing after that point was done. You can ask the team to pick it back up.{' '}
        <button className="link" onClick={() => setOpen(!open)}>
          {open ? 'Hide details' : 'Show details'}
        </button>
      </p>
      {open && <code className="details">{error}</code>}
    </section>
  )
}
