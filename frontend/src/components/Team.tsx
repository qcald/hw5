import type { AgentEvent } from '../api'
import { AGENTS, describeTool } from '../labels'
import { Avatar } from './Avatar'

type AgentState = { state: 'idle' | 'working' | 'done'; doing: string | null }

/** Work out what each agent is up to from the ticket's events. */
function agentStates(events: AgentEvent[], running: boolean): Record<string, AgentState> {
  const states: Record<string, AgentState> = {}
  for (const a of AGENTS) states[a.id] = { state: 'idle', doing: null }
  const open: Record<string, number> = {}
  for (const e of events) {
    const s = states[e.agent]
    if (!s) continue
    if (e.event === 'agent_started') {
      open[e.agent] = (open[e.agent] ?? 0) + 1
      s.doing = e.agent === 'boss' ? 'Reading the request and planning' : 'Picking up a task from the Boss'
    } else if (e.event === 'agent_finished') {
      open[e.agent] = Math.max(0, (open[e.agent] ?? 0) - 1)
      s.doing = 'Reported back'
    } else if (e.event === 'tool_call' || e.event === 'tool_error') {
      s.doing = describeTool(e)
    } else if (e.event === 'delegation') {
      s.doing = `Handed a task to ${AGENTS.find((a) => a.id === e.to)?.name ?? e.to}`
    } else if (e.event === 'approval_queued') {
      s.doing = 'Prepared a payment for your approval'
    }
    s.state = (open[e.agent] ?? 0) > 0 ? 'working' : 'done'
  }
  if (!running) for (const s of Object.values(states)) if (s.state === 'working') s.state = 'done'
  return states
}

export function Team({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const states = agentStates(events, running)
  return (
    <section className="team" aria-label="The team">
      {AGENTS.map((a) => {
        const s = states[a.id]
        const label = s.state === 'working' ? 'Working' : s.state === 'done' ? 'Done' : running ? 'Standing by' : 'Not involved yet'
        return (
          <div key={a.id} className={`member ${s.state}`}>
            <Avatar agent={a.id} size={32} />
            <div className="member-name">{a.name}</div>
            <div className="member-role">{a.role}</div>
            <div className="member-state">
              <span className="member-dot" aria-hidden />
              {label}
            </div>
            {s.state === 'working' && s.doing && <div className="member-doing">{s.doing}</div>}
          </div>
        )
      })}
    </section>
  )
}
