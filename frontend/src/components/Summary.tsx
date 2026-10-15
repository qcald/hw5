import { useState } from 'react'
import Markdown from 'react-markdown'
import type { AgentEvent } from '../api'
import { AGENTS, describeTool, money, shortSummary } from '../labels'
import { Avatar } from './Avatar'

function AgentSummary({ agent, report, actions }: { agent: string; report: string; actions: string[] }) {
  const [open, setOpen] = useState(false)
  const info = AGENTS.find((a) => a.id === agent)!
  return (
    <div className="summary-card">
      <div className="summary-head">
        <Avatar agent={agent} size={30} />
        <div>
          <div className="team-name">{info.name}</div>
          <div className="team-role">{info.role}</div>
        </div>
      </div>
      {open ? (
        <div className="report">
          <Markdown>{report}</Markdown>
        </div>
      ) : (
        <p className="summary-text">{shortSummary(report)}</p>
      )}
      {actions.length > 0 && (
        <ul className="summary-actions">
          {actions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}
      <button className="link" onClick={() => setOpen(!open)}>
        {open ? 'Show the short version' : 'Read the full report'}
      </button>
    </div>
  )
}

/** What each agent did on this request: its latest report plus the actions it took. */
export function Summary({ events }: { events: AgentEvent[] }) {
  const cards = AGENTS.flatMap((a) => {
    const reports = events.filter((e) => e.agent === a.id && e.event === 'agent_finished' && e.said)
    if (!reports.length) return []
    const actions = [
      ...new Set(
        events
          .filter((e) => e.agent === a.id && e.event === 'tool_call' && !['get_shop_date', 'get_ticket'].includes(e.tool ?? ''))
          .map(describeTool),
      ),
    ].slice(-5)
    return [<AgentSummary key={a.id} agent={a.id} report={reports[reports.length - 1].said!} actions={actions} />]
  })
  const decisions = events.filter((e) => e.agent === 'human' && (e.event === 'approval_result' || (e.event === 'approval_decision' && e.decision === 'denied')))
  if (decisions.length) {
    cards.push(
      <div key="human" className="summary-card you">
        <div className="summary-head">
          <Avatar agent="human" size={30} />
          <div>
            <div className="team-name">You</div>
            <div className="team-role">Approve or decline payments</div>
          </div>
        </div>
        <ul className="summary-actions">
          {decisions.map((e) => {
            const r = e.result as { paid?: boolean; payment?: { amount: number; approved_by: string }; new_balance?: number; error?: string } | undefined
            if (e.event === 'approval_decision') return <li key={e.seq}>Declined a payment the team prepared</li>
            return (
              <li key={e.seq}>
                {r?.paid && r.payment
                  ? `${r.payment.approved_by} approved a ${money(r.payment.amount)} payment. Checking went to ${money(Number(r.new_balance))}`
                  : `Approved a payment, but it didn't go through: ${r?.error ?? 'unknown reason'}`}
              </li>
            )
          })}
        </ul>
      </div>,
    )
  }
  if (!cards.length) return <p className="empty">Once the team has worked on this request, a short summary from each person shows up here.</p>
  return <div className="summary-grid">{cards}</div>
}
