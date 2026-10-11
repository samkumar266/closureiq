import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { DemoControls } from './components/DemoControls'
import { PRIMARY_FACILITY_ID } from './config'
import { DecisionRecord } from './pages/DecisionRecord'
import { DeliveryTracker } from './pages/DeliveryTracker'
import { FacilityDecision } from './pages/FacilityDecision'
// DEPRECATED(closureiq): the app opens on one facility (config.ts); the multi-facility Watchlist is retired.
// import { Watchlist } from './pages/Watchlist'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* DEPRECATED(closureiq): Watchlist landing page retired in favour of the single demo facility. */}
        {/* <Route path="/" element={<Watchlist />} /> */}
        <Route path="/" element={<Navigate replace to={`/facilities/${PRIMARY_FACILITY_ID}`} />} />
        <Route path="/facilities/:id" element={<FacilityDecision />} />
        <Route path="/notifications/:id" element={<DeliveryTracker />} />
        <Route path="/records/:id" element={<DecisionRecord />} />
      </Routes>
      <DemoControls />
    </BrowserRouter>
  )
}

export default App
