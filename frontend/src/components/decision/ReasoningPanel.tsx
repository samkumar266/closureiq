import { useState } from 'react'
import type { ConfidenceLevel, Recommendation } from '../../types'
import { PostureChip } from '../PostureChip'

type ReasoningPanelProps = {
  recommendation: Recommendation
}

const confidenceStyles: Record<ConfidenceLevel, string> = {
  high: 'bg-emerald-100 text-emerald-900',
  medium: 'bg-amber-100 text-amber-900',
  low: 'bg-red-600 text-white',
}

// "Forecast ice falls..." reads as "If forecast ice falls..."; acronyms such as NWS keep their case.
function lowerFirstWord(text: string) {
  const firstWord = text.split(' ')[0]
  return firstWord.length > 1 && firstWord === firstWord.toUpperCase() ? text : text.charAt(0).toLowerCase() + text.slice(1)
}

export function ReasoningPanel({ recommendation }: ReasoningPanelProps) {
  const [copied, setCopied] = useState(false)
  const { confidence } = recommendation

  const copyRationale = async () => {
    try {
      await navigator.clipboard.writeText(recommendation.rationale)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2_000)
    } catch (error) {
      console.warn('Unable to copy rationale', error)
    }
  }

  return (
    <div className="space-y-6">
      <section aria-label="Confidence" className="rounded-xl bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-bold text-slate-950">Confidence</h2>
          {/* Category and reasons only, never a percentage (architecture: Confidence). */}
          <span className={`rounded-full px-3 py-1 text-sm font-bold uppercase ${confidenceStyles[confidence.level]}`}>
            {confidence.level}
          </span>
        </div>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-800">
          {confidence.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </section>

      <section aria-label="What would change this" className="rounded-xl bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold text-slate-950">What would change this</h2>
        {recommendation.flip_list.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600">No nearby threshold would change the call.</p>
        ) : (
          <ul className="mt-3 space-y-3">
            {recommendation.flip_list.map((flip) => (
              <li className="text-sm text-slate-800" key={`${flip.change}-${flip.resulting_posture}`}>
                <p>
                  {/* DEPRECATED(closureiq): lowercased acronyms ("NWS" became "nWS"). */}
                  {/* If <strong>{flip.change.charAt(0).toLowerCase() + flip.change.slice(1)}</strong>, the engine would */}
                  If <strong>{lowerFirstWord(flip.change)}</strong>, the engine would
                  recommend <PostureChip posture={flip.resulting_posture} />
                </p>
                {flip.note && <p className="mt-1 text-xs text-slate-500">{flip.note}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Rationale" className="rounded-xl bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-bold text-slate-950">Rationale</h2>
          <button
            className="rounded-md border border-slate-300 px-3 py-1 text-sm font-medium text-slate-800 hover:bg-slate-100"
            onClick={() => void copyRationale()}
            type="button"
          >
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-slate-800">{recommendation.rationale}</p>
        <p className="mt-2 text-xs text-slate-500">Generated from the engine's values, not written by the AI.</p>
      </section>
    </div>
  )
}
