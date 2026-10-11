import { useRef, useState } from 'react'
import { ApiError, streamChat } from '../../api'

type AskPanelProps = {
  facilityId: string
  evaluationId: string
  offline: boolean
}

type Turn = {
  question: string
  answer: string
  tools: string[]
  // replaced: the number check failed and the engine's own rationale is shown instead.
  replaced: boolean
  validated: boolean | null
  hypothetical: boolean
  error: string | null
  streaming: boolean
}

const suggestions = [
  'Why is this the recommendation?',
  'What if the warning is upgraded to Severe?',
  'Which employees cannot telework?',
  'What evidence is missing or stale?',
]

export function AskPanel({ facilityId, evaluationId, offline }: AskPanelProps) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [draft, setDraft] = useState('')
  const [agentOffline, setAgentOffline] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const busy = turns.some((turn) => turn.streaming)

  const updateLast = (change: (turn: Turn) => Turn) =>
    setTurns((current) => current.map((turn, index) => (index === current.length - 1 ? change(turn) : turn)))

  const ask = async (question: string) => {
    if (!question.trim() || busy) return
    setDraft('')
    setTurns((current) => [
      ...current,
      { question, answer: '', tools: [], replaced: false, validated: null, hypothetical: false, error: null, streaming: true },
    ])
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await streamChat(
        { facility_id: facilityId, evaluation_id: evaluationId, message: question },
        (event) => {
          if (event.event === 'tool') {
            updateLast((turn) => ({
              ...turn,
              tools: turn.tools.includes(event.data.name) ? turn.tools : [...turn.tools, event.data.name],
              hypothetical: turn.hypothetical || event.data.name === 'run_what_if',
            }))
          } else if (event.event === 'token') {
            updateLast((turn) => ({ ...turn, answer: turn.answer + event.data.text }))
          } else if (event.event === 'replaced') {
            updateLast((turn) => ({ ...turn, answer: event.data.text, replaced: true }))
          } else if (event.event === 'done') {
            updateLast((turn) => ({
              ...turn,
              validated: event.data.validated,
              hypothetical: turn.hypothetical || Boolean(event.data.whatif_id),
              streaming: false,
            }))
          }
        },
        controller.signal,
      )
      updateLast((turn) => ({ ...turn, streaming: false }))
    } catch (error) {
      if (controller.signal.aborted) {
        updateLast((turn) => ({ ...turn, streaming: false, error: turn.answer ? null : 'Stopped.' }))
        return
      }
      const unavailable = error instanceof ApiError && (error.code === 'agent_unavailable' || error.status === 0)
      if (unavailable) setAgentOffline(true)
      updateLast((turn) => ({
        ...turn,
        streaming: false,
        error: unavailable ? 'The assistant is offline.' : error instanceof Error ? error.message : 'The question failed',
      }))
    }
  }

  return (
    <section aria-label="Ask about this recommendation" className="rounded-xl bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-950">Ask about this recommendation</h2>
        <p className="text-xs text-slate-500">The assistant explains. It cannot change, approve or send anything.</p>
      </div>

      {(offline || agentOffline) && (
        <p className="mt-3 rounded-md bg-slate-100 p-3 text-sm text-slate-700">
          Agent offline. The recommendation, rationale and approval do not depend on it.
        </p>
      )}

      <ol className="mt-4 space-y-4">
        {turns.map((turn, index) => (
          <li className="space-y-2" key={index}>
            <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-slate-900 px-3 py-2 text-sm text-white">{turn.question}</p>
            <div
              className={`max-w-[95%] rounded-lg border p-3 text-sm ${
                turn.hypothetical ? 'border-violet-400 bg-violet-50' : 'border-slate-200 bg-slate-50'
              }`}
            >
              {turn.hypothetical && (
                <p className="mb-1 text-xs font-bold uppercase tracking-wide text-violet-800">
                  Hypothetical: not the live recommendation, and it can never be approved
                </p>
              )}
              {turn.error ? (
                <p className="text-red-700">{turn.error}</p>
              ) : (
                <p className="whitespace-pre-wrap text-slate-800">{turn.answer || (turn.streaming ? 'Thinking…' : '')}</p>
              )}
              {turn.replaced && (
                <p className="mt-2 text-xs font-semibold text-amber-800">
                  A figure could not be verified, so the engine's own rationale is shown instead.
                </p>
              )}
              {turn.validated === true && !turn.replaced && (
                <p className="mt-2 text-xs text-emerald-700">✓ Every figure checked against the engine's data</p>
              )}
              {turn.tools.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {turn.tools.map((tool) => (
                    <span className="rounded bg-slate-200 px-1.5 py-0.5 font-mono text-[11px] text-slate-700" key={tool}>
                      {tool}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>

      <div className="mt-4 flex flex-wrap gap-2">
        {suggestions.map((suggestion) => (
          <button
            className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-100 disabled:opacity-50"
            disabled={busy || offline}
            key={suggestion}
            onClick={() => void ask(suggestion)}
            type="button"
          >
            {suggestion}
          </button>
        ))}
      </div>

      <form
        className="mt-3 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          void ask(draft)
        }}
      >
        <input
          aria-label="Your question"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          disabled={offline}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask a question or a what-if…"
          value={draft}
        />
        {busy ? (
          <button
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold"
            onClick={() => abortRef.current?.abort()}
            type="button"
          >
            Stop
          </button>
        ) : (
          <button
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            disabled={!draft.trim() || offline}
            type="submit"
          >
            Ask
          </button>
        )}
      </form>
    </section>
  )
}
