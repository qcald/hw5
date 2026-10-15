import { useState } from 'react'
import Markdown from 'react-markdown'

/** Markdown text that collapses to a few lines when long, with a link to expand it. */
export function Clamp({ text, limit = 420, more = 'Read more' }: { text: string; limit?: number; more?: string }) {
  const long = text.length > limit
  const [open, setOpen] = useState(false)
  return (
    <div className={`prose ${long && !open ? 'clamped' : ''}`}>
      <Markdown>{text}</Markdown>
      {long && (
        <button className="link more" onClick={() => setOpen(!open)}>
          {open ? 'Show less' : more}
        </button>
      )}
    </div>
  )
}
