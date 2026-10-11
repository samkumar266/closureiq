import { postureOrder, postureTheme, type Posture } from '../../theme'

type PostureScaleProps = {
  posture: Posture
  // What the engine computed before hysteresis; differs from posture only while a downgrade is held.
  rawPosture: Posture
}

// The graded recommendation as a green-to-red scale. Position comes only from the engine's posture
// (five stops), never from a score computed in the browser, and every stop is labelled, not colour alone.
export function PostureScale({ posture, rawPosture }: PostureScaleProps) {
  return (
    <div aria-label={`Operating status scale: ${postureTheme[posture].label}`} role="img">
      <div className="grid grid-cols-5 gap-1">
        {postureOrder.map((stop) => {
          const active = stop === posture
          const held = stop === rawPosture && rawPosture !== posture
          return (
            <div className="flex flex-col items-center" key={stop}>
              <span aria-hidden="true" className="h-5 text-lg leading-5" style={{ color: postureTheme[stop].color }}>
                {active ? '▼' : held ? '▽' : ''}
              </span>
              <div
                className={`h-4 w-full rounded-sm ${active ? 'ring-2 ring-slate-900 ring-offset-2' : 'opacity-35'}`}
                style={{ backgroundColor: postureTheme[stop].color }}
              />
              <span
                className={`mt-2 text-center text-xs leading-tight ${active ? 'font-bold text-slate-950' : 'text-slate-500'}`}
              >
                {postureTheme[stop].label}
              </span>
            </div>
          )
        })}
      </div>
      {rawPosture !== posture && (
        <p className="mt-2 text-xs text-slate-600">
          ▽ Latest reading points to {postureTheme[rawPosture].label.toLowerCase()}; held until two evaluations 15 minutes
          apart agree.
        </p>
      )}
    </div>
  )
}
