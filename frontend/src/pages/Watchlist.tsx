// DEPRECATED(closureiq) FILE: multi-facility Watchlist retired; the app opens on the single demo facility (config.ts).
// Entire file is commented out; delete it with the other DEPRECATED(closureiq) code.
// import { useCallback, useEffect, useMemo, useState } from 'react'
// import { getFacilities } from '../api'
// import { FacilityCard } from '../components/FacilityCard'
// import { StatusBadges } from '../components/StatusBadges'
// import { loadFacilities } from '../fixtures'
// import { useEventSource } from '../hooks/useEventSource'
// import { useServerClock } from '../hooks/useServerClock'
// import type { Posture } from '../theme'
// import type { AlertTier, Facility } from '../types'
//
// const postureOrder: Record<Posture, number> = {
//   closure: 0,
//   early_dismissal: 1,
//   delayed_arrival: 2,
//   unscheduled_leave_or_telework: 3,
//   normal_operations: 4,
// }
// const alertTierOrder: Record<AlertTier, number> = {
//   warning: 0,
//   watch: 1,
//   advisory: 2,
//   none: 3,
// }
//
// // Facilities not yet evaluated sort last within their alert tier.
// const postureRank = (facility: Facility) => (facility.current ? postureOrder[facility.current.posture] : 5)
//
// function sortFacilities(facilities: Facility[]) {
//   return [...facilities].sort(
//     (left, right) =>
//       alertTierOrder[left.highest_alert_tier] - alertTierOrder[right.highest_alert_tier] ||
//       postureRank(left) - postureRank(right),
//   )
// }
//
// export function Watchlist() {
//   const [facilities, setFacilities] = useState(loadFacilities)
//   const [fromFixture, setFromFixture] = useState(true)
//   const { subscribe, onReconnect } = useEventSource()
//   const { now, clockMode, speed, dataMode: serverDataMode } = useServerClock()
//   const dataMode = serverDataMode ?? facilities[0]?.data_mode ?? 'live'
//
//   const reloadFacilities = useCallback(
//     () =>
//       getFacilities().then((result) => {
//         setFacilities(result.facilities)
//         setFromFixture(result.fromFixture)
//       }),
//     [],
//   )
//
//   useEffect(() => {
//     getFacilities().then((result) => {
//       setFacilities(result.facilities)
//       setFromFixture(result.fromFixture)
//     })
//   }, [])
//
//   useEffect(() => {
//     // These events change card fields the event payload does not carry
//     // (headline, deadline, alert tier, approval status, source health), so refetch the list.
//     const refreshEvents = ['evaluation.created', 'approval.recorded', 'source.degraded', 'mode.changed'] as const
//     const unsubscribers = [
//       onReconnect(() => void reloadFacilities()),
//       ...refreshEvents.map((eventName) => subscribe(eventName, () => void reloadFacilities())),
//     ]
//
//     return () => unsubscribers.forEach((unsubscribe) => unsubscribe())
//   }, [onReconnect, reloadFacilities, subscribe])
//
//   const sortedFacilities = useMemo(() => sortFacilities(facilities), [facilities])
//
//   return (
//     <main className="min-h-screen bg-slate-50 px-6 py-8 text-slate-950 sm:px-10">
//       <div className="mx-auto max-w-6xl">
//         <header className="flex flex-wrap items-center justify-between gap-4">
//           <div>
//             <h1 className="text-3xl font-bold tracking-tight">Watchlist</h1>
//             <p className="mt-1 text-slate-600">Current facility operating recommendations</p>
//           </div>
//           <StatusBadges
//             clockMode={clockMode}
//             dataMode={dataMode}
//             fromFixture={fromFixture}
//             now={now}
//             speed={speed}
//           />
//         </header>
//
//         <section aria-label="Facility recommendations" className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
//           {sortedFacilities.map((facility) => (
//             <FacilityCard facility={facility} key={facility.facility_id} now={now} />
//           ))}
//         </section>
//       </div>
//     </main>
//   )
// }
