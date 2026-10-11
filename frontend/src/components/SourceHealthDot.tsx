// DEPRECATED(closureiq) FILE: only used by the retired FacilityCard.
// Entire file is commented out; delete it with the other DEPRECATED(closureiq) code.
// import type { SourceHealth } from '../types'
//
// type SourceHealthDotProps = {
//   sourceHealth: SourceHealth
// }
//
// const healthLabels: Record<SourceHealth, { label: string; color: string }> = {
//   ok: { label: 'Healthy', color: 'bg-emerald-600' },
//   degraded: { label: 'Stale', color: 'bg-amber-500' },
//   missing: { label: 'Missing', color: 'bg-red-600' },
// }
//
// export function SourceHealthDot({ sourceHealth }: SourceHealthDotProps) {
//   const health = healthLabels[sourceHealth]
//
//   return (
//     <span className="inline-flex items-center gap-2 text-sm text-slate-700">
//       <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${health.color}`} />
//       Source health: {health.label}
//     </span>
//   )
// }
