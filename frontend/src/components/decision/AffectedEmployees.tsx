// DEPRECATED(closureiq) FILE: merged into WhoGetsTold (timing, telework eligibility and each person's message).
// Entire file is commented out; delete it with the other DEPRECATED(closureiq) code.
// import { employeeGroups as groups } from '../../groups'
// import type { Employee } from '../../types'
//
// type AffectedEmployeesProps = {
//   employees: Employee[]
// }
//
// export function AffectedEmployees({ employees }: AffectedEmployeesProps) {
//   // Anyone in a group missing from employeeGroups still shows up, so nobody silently disappears.
//   const knownGroups = new Set<string>(groups.map((group) => group.id))
//   const ungrouped = employees.filter((employee) => !knownGroups.has(employee.group))
//   const sections = [
//     ...groups.map((group) => ({ ...group, members: employees.filter((employee) => employee.group === group.id) })),
//     { id: 'other', label: 'Other', note: 'Group not recognised by the UI', members: ungrouped },
//   ]
//
//   return (
//     <section aria-label="Affected employees" className="rounded-xl bg-white p-6 shadow-sm">
//       <div className="flex flex-wrap items-baseline justify-between gap-2">
//         <h2 className="text-lg font-bold text-slate-950">Affected employees by group</h2>
//         <p className="text-sm text-slate-600">{employees.length} people on the roster (synthetic names)</p>
//       </div>
//       {employees.length === 0 ? (
//         <p className="mt-3 text-sm text-slate-600">No roster available for this facility.</p>
//       ) : (
//         <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
//           {sections.map(({ members, ...group }) => {
//             if (members.length === 0) return null
//             return (
//               <details className="rounded-lg border border-slate-200 p-3" key={group.id}>
//                 <summary className="cursor-pointer">
//                   <span className="text-2xl font-bold text-slate-950">{members.length}</span>{' '}
//                   <span className="font-semibold text-slate-900">{group.label}</span>
//                   <span className="block text-xs text-slate-500">{group.note}</span>
//                 </summary>
//                 <ul className="mt-2 space-y-1 text-sm text-slate-800">
//                   {members.map((employee) => (
//                     <li key={employee.employee_id}>
//                       {employee.name}{' '}
//                       <span className="text-xs text-slate-500">
//                         {employee.shift_start}–{employee.shift_end}
//                         {employee.comm_needs.length > 0 && ' · alternate format or language'}
//                       </span>
//                     </li>
//                   ))}
//                 </ul>
//               </details>
//             )
//           })}
//         </div>
//       )}
//     </section>
//   )
// }
