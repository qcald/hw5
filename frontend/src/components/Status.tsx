import { statusLook } from '../labels'

/** A quiet status indicator: colored dot plus a plain-language label. */
export function Status({ status, running, large = false }: { status: string; running: boolean; large?: boolean }) {
  const look = statusLook(status, running)
  return (
    <span className={`status ${look.tone} ${large ? 'large' : ''}`}>
      <span className="status-dot" aria-hidden />
      {look.label}
    </span>
  )
}
