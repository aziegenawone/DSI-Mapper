import SiteMap from '../../components/Map/SiteMap'

export default function FlightPlanner() {
  return (
    <div>
      <div className="page-header">
        <h2>Flight Planner</h2>
        <p>Plan inspection flights and export KMZ for DJI Pilot 2</p>
      </div>
      <SiteMap />
      {/* TODO: site boundary editor, flight params panel, KMZ export button */}
    </div>
  )
}
