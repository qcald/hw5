// Small line icons so each kind of request is recognizable at a glance.

export function TicketIcon({ type }: { type: string }) {
  const common = { width: 22, height: 22, fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  let path
  if (type === 'customer_order') {
    // t-shirt
    path = <path d="M8 3 4 5.5 2.5 9.5l3 1.5V21h13V11l3-1.5L20 5.5 16 3c-.6 1.6-2.2 2.6-4 2.6S8.6 4.6 8 3Z" />
  } else if (type === 'rent_notice') {
    // storefront
    path = (
      <>
        <path d="M3 10h18v11H3z" />
        <path d="M3 10 5 4h14l2 6" />
        <path d="M10 21v-6h4v6" />
      </>
    )
  } else {
    // price tag
    path = (
      <>
        <path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9-9-9Z" />
        <circle cx="7.5" cy="7.5" r="1.5" />
      </>
    )
  }
  return (
    <span className="ticket-icon" aria-hidden>
      <svg viewBox="0 0 24 24" {...common}>
        {path}
      </svg>
    </span>
  )
}
