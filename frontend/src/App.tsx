import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { FacilityDecision } from './pages/FacilityDecision'
import { Watchlist } from './pages/Watchlist'

function Record() {
  return (
    <main className="min-h-screen p-8">
      <h1 className="text-3xl font-semibold">Decision record</h1>
      <p className="mt-2 text-slate-600">Record details will appear here.</p>
    </main>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Watchlist />} />
        <Route path="/facilities/:id" element={<FacilityDecision />} />
        <Route path="/records/:id" element={<Record />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
