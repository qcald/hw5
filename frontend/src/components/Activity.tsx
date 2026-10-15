import { useState } from 'react'
import type { AgentEvent } from '../api'
import { agentById, describeTool, money, niceTime } from '../labels'
import { Avatar, agentName } from './Avatar'
import { Clamp } from './Clamp'

// Routine lookups that add noise without telling a person anything new.
const ROUTINE_TOOLS = new Set(['get_shop_date', 'get_ticket', 'list_open_tickets', 'list_tickets'])

type Item =
  | { kind: 'event'; e: AgentEvent }
  | { kind: 'actions'; agent: string; events: AgentEvent[] }

/** Collapse each agent's back-to-back tool calls into one group, skipping routine lookups. */
function toItems(events: AgentEvent[]): Item[] {
  const items: Item[] = []
  for (const e of events) {
    if (e.event === 'tool_call' || e.event === 'tool_error') {
      if (e.event === 'tool_call' && ROUTINE_TOOLS.has(e.tool ?? '')) continue
      const last = items[items.length - 1]
      if (last?.kind === 'actions' && last.agent === e.agent) last.events.push(e)
      else items.push({ kind: 'actions', agent: e.agent, events: [e] })
    } else {
      items.push({ kind: 'event', e })
    }
  }
  return items
}

function Failure({ e }: { e: AgentEvent }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="marker error">
      <span>The team stopped before finishing · {niceTime(e.ts)}</span>
      <button className="link" onClick={() => setOpen(!open)}>
        {open ? 'Hide details' : 'Details'}
      </button>
      {open && <code className="details">{e.said}</code>}
    </div>
  )
}

function Entry({ item }: { item: Item }) {
  if (item.kind === 'actions') {
    return (
      <div className="actions">
        <div className="actions-who">{agentName(item.agent)}</div>
        <ul>
          {item.events.map((e) => (
            <li key={e.seq} className={e.event === 'tool_error' ? 'error' : ''}>
              {describeTool(e)}
            </li>
          ))}
        </ul>
      </div>
    )
  }
  const e = item.e
  switch (e.event) {
    case 'run_started':
      return <div className="marker">The team started · {niceTime(e.ts)}</div>
    case 'run_finished':
      return <div className="marker">The team finished · {niceTime(e.ts)}</div>
    case 'run_failed':
      return <Failure e={e} />
    case 'delegation':
      return (
        <div className="message">
          <Avatar agent="boss" size={30} />
          <div className="message-body">
            <div className="message-who">
              Boss <span className="message-to">to {agentById(e.to ?? '')?.name ?? e.to}</span>
            </div>
            <Clamp text={e.said ?? ''} limit={260} />
          </div>
        </div>
      )
    case 'agent_finished':
      return (
        <div className="message report">
          <Avatar agent={e.agent} size={30} />
          <div className="message-body">
            <div className="message-who">
              {agentName(e.agent)} <span className="message-to">{e.agent === 'boss' ? 'wrap-up' : 'reported back'}</span>
            </div>
            <Clamp text={e.said ?? ''} limit={480} more="Read the full report" />
          </div>
        </div>
      )
    case 'approval_queued':
      return <div className="note attention">Accounting prepared a payment for your approval</div>
    case 'approval_decision':
      return (
        <div className={`note ${e.decision === 'approved' ? 'ok' : ''}`}>
          {e.agent === 'human' ? (e.approved_by ?? 'You') : agentName(e.agent)}{' '}
          {e.decision === 'approved' ? 'approved the payment' : 'declined the payment'}
        </div>
      )
    case 'approval_result': {
      const r = e.result as { paid?: boolean; new_balance?: number; error?: string } | undefined
      return r?.paid ? (
        <div className="note ok">Payment sent. Checking is now {money(Number(r.new_balance))}</div>
      ) : (
        <div className="note error">The payment didn't go through: {r?.error ?? 'unknown reason'}</div>
      )
    }
    default:
      return null
  }
}

const SHOWN = new Set([
  'run_started', 'run_finished', 'run_failed', 'delegation', 'agent_finished', 'tool_call', 'tool_error',
  'approval_queued', 'approval_decision', 'approval_result',
])

export function Activity({ events }: { events: AgentEvent[] }) {
  const items = toItems(events.filter((e) => SHOWN.has(e.event)))
  if (!items.length) return <p className="empty">Nothing yet. Start the team and each step will appear here as it happens.</p>
  return (
    <div className="timeline">
      {items.map((item) => (
        <Entry key={item.kind === 'event' ? item.e.seq : `a${item.events[0].seq}`} item={item} />
      ))}
    </div>
  )
}
