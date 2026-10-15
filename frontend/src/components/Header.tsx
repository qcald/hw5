import type { Cash } from '../api'
import { money, niceDate } from '../labels'

type Props = {
  shopDate: string | null
  cash: Cash | null
  lastChange: number | null
}

export function Header({ shopDate, cash, lastChange }: Props) {
  return (
    <header className="header">
      <div className="header-inner">
        <div className="brand">
          <span className="brand-mark">CC</span>
          <div>
            <div className="brand-name">Campus Customs</div>
            <div className="brand-sub">Front Desk</div>
          </div>
        </div>

        <div className="header-stats">
          {shopDate && (
            <div className="stat">
              <div className="stat-label">Today</div>
              <div className="stat-value small">{niceDate(shopDate)}</div>
            </div>
          )}
          <div className="stat" aria-live="polite">
            <div className="stat-label">Checking</div>
            <div className="stat-value">{cash ? money(cash.balance) : '—'}</div>
            {lastChange !== null && lastChange !== 0 && (
              <div className={`stat-change ${lastChange < 0 ? 'down' : 'up'}`}>
                {lastChange < 0 ? '−' : '+'}
                {money(Math.abs(lastChange))} last payment
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}
