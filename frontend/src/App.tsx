import { Routes, Route, NavLink } from 'react-router-dom'
import FlightPlanner from './pages/FlightPlanner'
import DataIngestion from './pages/DataIngestion'
import Analysis from './pages/Analysis'
import DigitalTwin from './pages/DigitalTwin'
import Reports from './pages/Reports'
import SerialReader from './pages/SerialReader'

function App() {
  return (
    <div className="app-layout">
      <aside className="sidebar">
        <h1>DSI Mapper</h1>
        <nav>
          <NavLink to="/">Flight Planner</NavLink>
          <NavLink to="/ingestion">Data Ingestion</NavLink>
          <NavLink to="/analysis">Analysis</NavLink>
          <NavLink to="/twin">Digital Twin</NavLink>
          <NavLink to="/reports">Reports</NavLink>
          <NavLink to="/serials">Serial Reader</NavLink>
        </nav>
      </aside>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<FlightPlanner />} />
          <Route path="/ingestion" element={<DataIngestion />} />
          <Route path="/analysis" element={<Analysis />} />
          <Route path="/twin" element={<DigitalTwin />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/serials" element={<SerialReader />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
