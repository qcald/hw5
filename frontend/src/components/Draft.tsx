import { useState } from 'react'
import { niceDate } from '../labels'

const LONG = 360

/** One drafted message, shown like a letter: who it's to, the full text with its line breaks, and a copy button. */
export function Draft({ to, date, text }: { to: string; date: string; text: string }) {
  const long = text.length > LONG
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  return (
    <div className="draft">
      <div className="draft-head">
        <div>
          <div className="draft-to">To {to}</div>
          <div className="draft-meta">Drafted {niceDate(date)} · not sent</div>
        </div>
        <button className="btn ghost small" onClick={copy}>
          {copied ? 'Copied' : 'Copy text'}
        </button>
      </div>
      <div className={`draft-text ${long && !open ? 'clamped' : ''}`}>{text}</div>
      {long && (
        <button className="link" onClick={() => setOpen(!open)}>
          {open ? 'Show less' : 'Show the whole message'}
        </button>
      )}
    </div>
  )
}
