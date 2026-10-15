import { agentById } from '../labels'

export function Avatar({ agent, size = 36 }: { agent: string; size?: number }) {
  const info = agentById(agent)
  const isHuman = agent === 'human'
  return (
    <span
      className="avatar"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.36,
        background: isHuman ? '#F2C14E' : (info?.color ?? '#6b7280'),
        color: isHuman ? '#3b2f0b' : '#fff',
      }}
      aria-hidden
    >
      {isHuman ? 'You' : (info?.initials ?? '?')}
    </span>
  )
}

export const agentName = (agent: string) =>
  agent === 'human' ? 'You' : agent === 'harness' ? 'Front desk' : (agentById(agent)?.name ?? agent)
