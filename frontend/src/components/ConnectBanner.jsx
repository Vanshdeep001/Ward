import { Link } from 'react-router-dom'
import { ArrowRight, Plug } from 'lucide-react'

// Shown while Ward is reading the demo account. Its own module so pages that show it don't pull the
// whole connect flow into their chunk.
export default function ConnectBanner() {
  return (
    <Link
      to="/connect"
      className="group mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-arc-100 bg-arc-50/70 px-4 py-3 transition hover:border-arc-200 hover:bg-arc-50"
    >
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-arc-600 text-white"><Plug size={15} /></span>
      <span className="min-w-0 flex-1 text-[13.5px] text-slate-700">
        <span className="font-semibold text-ink">You’re looking at a demo account.</span> Connect your own to watch real
        resources — read-only, no access keys.
      </span>
      <span className="flex shrink-0 items-center gap-1 text-[12px] font-bold text-arc-700">
        Connect <ArrowRight size={13} className="transition group-hover:translate-x-0.5" />
      </span>
    </Link>
  )
}
