// DEPRECATED(closureiq) FILE: replaced by EvidenceSummary (plain-language reasons, grouped, no raw field names).
// Entire file is commented out; delete it with the other DEPRECATED(closureiq) code.
// import { formatDateTime, formatDuration, formatNumber, formatTime, formatValue } from '../../format'
// import type { Recommendation, ThresholdCrossed, ThresholdNotCrossed } from '../../types'
//
// type EvidencePanelProps = {
//   recommendation: Recommendation
//   timeZone: string
// }
//
// function formatCutoffValue(value: string | number, unit?: string) {
//   return typeof value === 'number' ? `${formatNumber(value)}${unit ? ` ${unit}` : ''}` : value
// }
//
// function CrossedRow({ threshold, label }: { threshold: ThresholdCrossed; label: string }) {
//   return (
//     <li className="rounded-lg border border-red-200 bg-red-50 p-3">
//       <p className="text-sm font-semibold text-slate-950">
//         {threshold.id} · {label}
//       </p>
//       <p className="mt-1 text-sm text-slate-800">
//         Actual <strong>{formatCutoffValue(threshold.actual, threshold.unit)}</strong> against cutoff{' '}
//         {formatCutoffValue(threshold.cutoff, threshold.unit)}
//         {threshold.margin !== undefined && threshold.margin !== null && (
//           <span className="font-semibold text-red-800">
//             {' '}
//             · over by {formatNumber(threshold.margin)} {threshold.unit}
//           </span>
//         )}
//       </p>
//       {threshold.anchor && (
//         <p className="mt-1 text-xs text-slate-600">
//           Source:{' '}
//           {threshold.anchor_url ? (
//             <a className="underline" href={threshold.anchor_url} rel="noreferrer" target="_blank">
//               {threshold.anchor}
//             </a>
//           ) : (
//             threshold.anchor
//           )}
//         </p>
//       )}
//     </li>
//   )
// }
//
// function NotCrossedRow({ threshold, label }: { threshold: ThresholdNotCrossed; label: string }) {
//   return (
//     <li className="rounded-lg border border-slate-200 p-3">
//       <p className="text-sm font-semibold text-slate-950">
//         {threshold.id} · {label}
//       </p>
//       <p className="mt-1 text-sm text-slate-700">
//         Actual {formatCutoffValue(threshold.actual, threshold.unit)} against cutoff{' '}
//         {formatCutoffValue(threshold.cutoff, threshold.unit)}
//         {threshold.distance !== undefined && threshold.distance !== null && (
//           <> · {formatNumber(threshold.distance)} {threshold.unit} below</>
//         )}
//       </p>
//     </li>
//   )
// }
//
// export function EvidencePanel({ recommendation, timeZone }: EvidencePanelProps) {
//   const evaluatedAt = new Date(recommendation.evaluated_at).getTime()
//   const inputLabel = (inputId: string) =>
//     recommendation.inputs.find((input) => input.id === inputId)?.label ?? inputId
//
//   return (
//     <section aria-label="Evidence" className="rounded-xl bg-white p-6 shadow-sm">
//       <h2 className="text-lg font-bold text-slate-950">Evidence</h2>
//       <ul className="mt-3 space-y-3">
//         {recommendation.inputs.map((input) => (
//           <li className="rounded-lg border border-slate-200 p-3" key={input.id}>
//             <div className="flex flex-wrap items-center gap-2">
//               <span className="font-semibold text-slate-950">{input.label}</span>
//               <span
//                 className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
//                   input.role === 'drove' ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700'
//                 }`}
//                 title={input.role === 'drove' ? 'This input drove the recommendation' : 'Checked and ruled out'}
//               >
//                 {input.role === 'drove' ? 'Drove the call' : 'Checked, not a factor'}
//               </span>
//               {input.stale && (
//                 <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">
//                   STALE
//                 </span>
//               )}
//             </div>
//             <p className="mt-1 text-sm text-slate-800">{formatValue(input.value, input.unit)}</p>
//             {input.onset && input.ends && (
//               <p className="mt-1 text-sm text-slate-700">
//                 In effect {formatDateTime(input.onset, timeZone)} to {formatDateTime(input.ends, timeZone)}
//               </p>
//             )}
//             <p className="mt-1 text-xs text-slate-500">
//               {input.source} · fetched {formatTime(input.fetched_at, timeZone)} (
//               {formatDuration((evaluatedAt - new Date(input.fetched_at).getTime()) / 1_000)} before evaluation) ·{' '}
//               {input.snapshot_id}
//             </p>
//           </li>
//         ))}
//       </ul>
//
//       <h3 className="mt-6 font-bold text-slate-950">Thresholds crossed</h3>
//       {recommendation.thresholds_crossed.length === 0 ? (
//         <p className="mt-2 text-sm text-slate-600">No threshold crossed.</p>
//       ) : (
//         <ul className="mt-2 space-y-2">
//           {recommendation.thresholds_crossed.map((threshold) => (
//             <CrossedRow key={threshold.id} label={inputLabel(threshold.input_id)} threshold={threshold} />
//           ))}
//         </ul>
//       )}
//
//       {recommendation.thresholds_not_crossed.length > 0 && (
//         <>
//           <h3 className="mt-6 font-bold text-slate-950">Checked and not crossed</h3>
//           <ul className="mt-2 space-y-2">
//             {recommendation.thresholds_not_crossed.map((threshold) => (
//               <NotCrossedRow key={threshold.id} label={inputLabel(threshold.input_id)} threshold={threshold} />
//             ))}
//           </ul>
//         </>
//       )}
//     </section>
//   )
// }
