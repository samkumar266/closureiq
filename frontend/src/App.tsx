import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { DemoControls } from './components/DemoControls'
import { DecisionRecord } from './pages/DecisionRecord'
import { DeliveryTracker } from './pages/DeliveryTracker'
import { FacilityDecision } from './pages/FacilityDecision'
import { Watchlist } from './pages/Watchlist'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Watchlist />} />
        <Route path="/facilities/:id" element={<FacilityDecision />} />
        <Route path="/notifications/:id" element={<DeliveryTracker />} />
        <Route path="/records/:id" element={<DecisionRecord />} />
      </Routes>
      <DemoControls />
    </BrowserRouter>
  )
}

export default App
