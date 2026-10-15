import { useState } from 'react'
import type { Approval } from '../api'
import { describeApproval, money } from '../labels'
import { agentName } from './Avatar'

type Props = {
  approval: Approval
  approverName: string
  onApproverName: (name: string) => void
  onDecide: (approval: Approval, decision: 'approve' | 'deny') => Promise<void>
}

export function ApprovalCard({ approval, approverName, onApproverName, onDecide }: Props) {
  const [busy, setBusy] = useState<'approve' | 'deny' | null>(null)
  const d = describeApproval(approval)
  const decide = async (decision: 'approve' | 'deny') => {
    setBusy(decision)
    try {
      await onDecide(approval, decision)
    } finally {
      setBusy(null)
    }
  }
  return (
    <section className="approval" aria-label="Payment waiting for approval">
      <div className="approval-top">
        <div>
          <div className="eyebrow attention">Approval needed</div>
          <div className="approval-amount">{d.amount !== null ? money(d.amount) : 'Payment'}</div>
          <p className="approval-what">{d.what}</p>
        </div>
        {d.before !== null && d.after !== null && (
          <dl className="approval-balance">
            <div>
              <dt>Checking now</dt>
              <dd>{money(d.before)}</dd>
            </div>
            <div>
              <dt>After payment</dt>
              <dd>{money(d.after)}</dd>
            </div>
          </dl>
        )}
      </div>
      <div className="approval-actions">
        <label className="field">
          <span>Your name</span>
          <input
            value={approverName}
            onChange={(e) => onApproverName(e.target.value)}
            placeholder="Required to approve"
            autoComplete="name"
          />
        </label>
        <button className="btn primary" disabled={!approverName.trim() || busy !== null} onClick={() => decide('approve')}>
          {busy === 'approve' ? 'Paying…' : 'Approve payment'}
        </button>
        <button className="btn ghost" disabled={busy !== null} onClick={() => decide('deny')}>
          {busy === 'deny' ? 'Declining…' : 'Decline'}
        </button>
      </div>
      <p className="approval-note">
        Prepared by {agentName(approval.requested_by)}. Nothing is paid until you approve.
      </p>
    </section>
  )
}
