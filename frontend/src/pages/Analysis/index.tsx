import SiteMap from '../../components/Map/SiteMap'

export default function Analysis() {
  return (
    <div>
      <div className="page-header">
        <h2>Analysis</h2>
        <p>AI detection results: panels, defects, thermal anomalies</p>
      </div>
      <SiteMap />
      {/* TODO: orthophoto overlay, defect markers, panel polygons, filter sidebar */}
    </div>
  )
}
