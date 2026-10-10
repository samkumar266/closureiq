import { BrowserRouter, Route, Routes } from 'react-router-dom'

function Watchlist() {
  return (
    <main className="min-h-screen p-8">
      <h1 className="text-3xl font-semibold">Watchlist</h1>
      <p className="mt-2 text-slate-600">Facilities requiring attention will appear here.</p>
    </main>
  )
}

function Facility() {
  return (
    <main className="min-h-screen p-8">
      <h1 className="text-3xl font-semibold">Facility</h1>
      <p className="mt-2 text-slate-600">Facility details will appear here.</p>
    </main>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Watchlist />} />
        <Route path="/facilities/:id" element={<Facility />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
