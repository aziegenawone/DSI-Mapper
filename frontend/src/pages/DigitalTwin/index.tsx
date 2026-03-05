import SiteMap from '../../components/Map/SiteMap'

export default function DigitalTwin() {
  return (
    <div>
      <div className="page-header">
        <h2>Digital Twin</h2>
        <p>Plant asset database with panel history and degradation trends</p>
      </div>
      <SiteMap />
      {/* TODO: panel click → history sidebar, trend charts, heatmap overlay */}
    </div>
  )
}
