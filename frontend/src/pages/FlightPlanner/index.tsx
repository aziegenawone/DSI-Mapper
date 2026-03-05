import { useState, useEffect, useCallback, useRef } from 'react'
import { MapContainer, TileLayer, Polyline, Marker, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet-draw/dist/leaflet.draw.css'
import 'leaflet-draw'

import {
  flightPlannerApi,
  type FlightPlanRequest,
  type FlightPlanResponse,
  type CameraPreset,
} from '../../lib/api'

// ── Leaflet default icon fix (Vite asset hashing breaks the default icon) ────
import iconUrl from 'leaflet/dist/images/marker-icon.png'
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png'
import shadowUrl from 'leaflet/dist/images/marker-shadow.png'

delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl
L.Icon.Default.mergeOptions({ iconUrl, iconRetinaUrl, shadowUrl })

// ── Small waypoint icon ───────────────────────────────────────────────────────
const waypointIcon = (color: string) =>
  L.divIcon({
    className: '',
    html: `<div style="
      width:10px;height:10px;border-radius:50%;
      background:${color};border:2px solid #fff;
      box-shadow:0 0 4px rgba(0,0,0,0.6);
    "></div>`,
    iconSize: [10, 10],
    iconAnchor: [5, 5],
  })

// Row colours cycle (up to 20 rows)
const ROW_COLORS = [
  '#00d4ff', '#ff6b35', '#7bc67e', '#ffd166', '#c77dff',
  '#ff4d6d', '#4ecdc4', '#f7b731', '#a29bfe', '#fd79a8',
  '#55efc4', '#fdcb6e', '#e17055', '#74b9ff', '#b2bec3',
  '#6c5ce7', '#00b894', '#e84393', '#d63031', '#0984e3',
]

// ── DrawControl component – integrates leaflet-draw imperatively ──────────────
interface DrawControlProps {
  onPolygonCreated: (coords: number[][]) => void
}

function DrawControl({ onPolygonCreated }: DrawControlProps) {
  const map = useMap()
  const drawnItemsRef = useRef<L.FeatureGroup | null>(null)

  useEffect(() => {
    if (!map) return

    const drawnItems = new L.FeatureGroup()
    drawnItemsRef.current = drawnItems
    map.addLayer(drawnItems)

    const drawControl = new (L.Control as unknown as {
      Draw: new (opts: unknown) => L.Control
    }).Draw({
      edit: {
        featureGroup: drawnItems,
        remove: true,
      },
      draw: {
        polygon: {
          allowIntersection: false,
          showArea: true,
          shapeOptions: {
            color: '#6c5ce7',
            fillColor: '#6c5ce7',
            fillOpacity: 0.15,
            weight: 2,
          },
        },
        polyline: false,
        rectangle: {
          shapeOptions: {
            color: '#6c5ce7',
            fillColor: '#6c5ce7',
            fillOpacity: 0.15,
            weight: 2,
          },
        },
        circle: false,
        circlemarker: false,
        marker: false,
      },
    })

    map.addControl(drawControl)

    const handleCreated = (e: L.LeafletEvent) => {
      const event = e as L.DrawEvents.Created
      // Clear previous drawings
      drawnItems.clearLayers()
      drawnItems.addLayer(event.layer)

      const layer = event.layer as L.Polygon | L.Rectangle
      const latLngs = layer.getLatLngs()

      // Flatten the first ring of the polygon
      const ring = Array.isArray(latLngs[0]) ? latLngs[0] : latLngs
      const coords = (ring as L.LatLng[]).map((ll) => [ll.lat, ll.lng])
      onPolygonCreated(coords)
    }

    const handleEdited = (e: L.LeafletEvent) => {
      const event = e as L.DrawEvents.Edited
      event.layers.eachLayer((layer) => {
        const poly = layer as L.Polygon
        const latLngs = poly.getLatLngs()
        const ring = Array.isArray(latLngs[0]) ? latLngs[0] : latLngs
        const coords = (ring as L.LatLng[]).map((ll) => [ll.lat, ll.lng])
        onPolygonCreated(coords)
      })
    }

    const handleDeleted = () => {
      onPolygonCreated([])
    }

    map.on(L.Draw.Event.CREATED, handleCreated)
    map.on(L.Draw.Event.EDITED, handleEdited)
    map.on(L.Draw.Event.DELETED, handleDeleted)

    return () => {
      map.off(L.Draw.Event.CREATED, handleCreated)
      map.off(L.Draw.Event.EDITED, handleEdited)
      map.off(L.Draw.Event.DELETED, handleDeleted)
      map.removeControl(drawControl)
      map.removeLayer(drawnItems)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map])

  return null
}

// ── Default form values ───────────────────────────────────────────────────────
const DEFAULT_PARAMS: Omit<FlightPlanRequest, 'boundary_coords' | 'camera_preset_key'> = {
  num_rows: 10,
  gsd_cm_px: 1.5,
  rotation_deg: 0,
  is_vertical: false,
  zoom_ratio: 1.0,
  object_height_m: 0,
  flight_speed_ms: 5,
  gimbal_pitch_deg: -90,
  photo_interval_s: 2,
  aircraft_yaw_deg: 0,
  mission_name: 'Mission 01',
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  if (m === 0) return `${s}s`
  return `${m}m ${s}s`
}

function formatDistance(meters: number): string {
  if (meters >= 1000) return `${(meters / 1000).toFixed(2)} km`
  return `${Math.round(meters)} m`
}

// ── Main component ────────────────────────────────────────────────────────────
export default function FlightPlanner() {
  // Form state
  const [missionName, setMissionName] = useState(DEFAULT_PARAMS.mission_name)
  const [cameraKey, setCameraKey] = useState('')
  const [gsd, setGsd] = useState(DEFAULT_PARAMS.gsd_cm_px)
  const [numRows, setNumRows] = useState(DEFAULT_PARAMS.num_rows)
  const [flightSpeed, setFlightSpeed] = useState(DEFAULT_PARAMS.flight_speed_ms)
  const [zoomRatio, setZoomRatio] = useState(DEFAULT_PARAMS.zoom_ratio)
  const [rotation, setRotation] = useState(DEFAULT_PARAMS.rotation_deg)
  const [gimbalPitch, setGimbalPitch] = useState(DEFAULT_PARAMS.gimbal_pitch_deg)
  const [photoInterval, setPhotoInterval] = useState(DEFAULT_PARAMS.photo_interval_s)
  const [objectHeight, setObjectHeight] = useState(DEFAULT_PARAMS.object_height_m)
  const [aircraftYaw, setAircraftYaw] = useState(DEFAULT_PARAMS.aircraft_yaw_deg)
  const [isVertical, setIsVertical] = useState(DEFAULT_PARAMS.is_vertical)

  // Map / data state
  const [boundaryCoords, setBoundaryCoords] = useState<number[][]>([])
  const [cameraPresets, setCameraPresets] = useState<Record<string, CameraPreset>>({})
  const [planResult, setPlanResult] = useState<FlightPlanResponse | null>(null)

  // UI state
  const [loadingPresets, setLoadingPresets] = useState(true)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [loadingExport, setLoadingExport] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [presetsError, setPresetsError] = useState<string | null>(null)

  // ── Load camera presets on mount ───────────────────────────────────────────
  useEffect(() => {
    setLoadingPresets(true)
    flightPlannerApi
      .getCameraPresets()
      .then((data) => {
        setCameraPresets(data)
        const firstKey = Object.keys(data)[0]
        if (firstKey) setCameraKey(firstKey)
      })
      .catch((err) => {
        const msg = err?.response?.data?.detail ?? err?.message ?? 'Failed to load camera presets'
        setPresetsError(msg)
        // Provide a fallback so the form is still usable
        setCameraKey('dji_zenmuse_x7')
      })
      .finally(() => setLoadingPresets(false))
  }, [])

  // ── Build request object ───────────────────────────────────────────────────
  const buildRequest = useCallback((): FlightPlanRequest => ({
    boundary_coords: boundaryCoords,
    num_rows: numRows,
    gsd_cm_px: gsd,
    camera_preset_key: cameraKey,
    rotation_deg: rotation,
    is_vertical: isVertical,
    zoom_ratio: zoomRatio,
    object_height_m: objectHeight,
    flight_speed_ms: flightSpeed,
    gimbal_pitch_deg: gimbalPitch,
    photo_interval_s: photoInterval,
    aircraft_yaw_deg: aircraftYaw,
    mission_name: missionName,
  }), [
    boundaryCoords, numRows, gsd, cameraKey, rotation,
    isVertical, zoomRatio, objectHeight, flightSpeed,
    gimbalPitch, photoInterval, aircraftYaw, missionName,
  ])

  // ── Preview ────────────────────────────────────────────────────────────────
  const handlePreview = useCallback(async () => {
    if (boundaryCoords.length < 3) {
      setError('Draw a polygon boundary on the map first.')
      return
    }
    if (!cameraKey) {
      setError('Select a camera preset.')
      return
    }
    setError(null)
    setLoadingPreview(true)
    try {
      const result = await flightPlannerApi.previewPlan(buildRequest())
      setPlanResult(result)
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string }
      setError(e?.response?.data?.detail ?? e?.message ?? 'Preview failed')
    } finally {
      setLoadingPreview(false)
    }
  }, [boundaryCoords, cameraKey, buildRequest])

  // ── KMZ Export ────────────────────────────────────────────────────────────
  const handleExportKmz = useCallback(async () => {
    if (boundaryCoords.length < 3) {
      setError('Draw a polygon boundary on the map first.')
      return
    }
    setError(null)
    setLoadingExport(true)
    try {
      const response = await flightPlannerApi.exportKmz(buildRequest())
      const blob = new Blob([response.data as BlobPart], { type: 'application/vnd.google-earth.kmz' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${missionName.replace(/\s+/g, '_')}.kmz`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string }
      setError(e?.response?.data?.detail ?? e?.message ?? 'KMZ export failed')
    } finally {
      setLoadingExport(false)
    }
  }, [boundaryCoords, buildRequest, missionName])

  // ── Polygon drawn callback ─────────────────────────────────────────────────
  const handlePolygonCreated = useCallback((coords: number[][]) => {
    setBoundaryCoords(coords)
    setPlanResult(null)
    setError(null)
  }, [])

  // ── Waypoints grouped by row ───────────────────────────────────────────────
  type Waypoint = FlightPlanResponse['waypoints'][number]
  const waypointsByRow: Record<number, Waypoint[]> = {}
  if (planResult) {
    for (const wp of planResult.waypoints) {
      if (!waypointsByRow[wp.row_index]) waypointsByRow[wp.row_index] = []
      waypointsByRow[wp.row_index].push(wp)
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={styles.pageRoot}>
      {/* ── Left Sidebar ─────────────────────────────────────────── */}
      <aside style={styles.sidebar}>
        <div style={styles.sidebarInner}>
          {/* Header */}
          <div style={styles.sidebarHeader}>
            <h2 style={styles.sidebarTitle}>Flight Planner</h2>
            <p style={styles.sidebarSubtitle}>Plan inspection flights &amp; export KMZ for DJI Pilot 2</p>
          </div>

          {/* Error / preset error banners */}
          {presetsError && (
            <div style={{ ...styles.banner, ...styles.bannerWarning }}>
              Camera presets unavailable: {presetsError}
            </div>
          )}
          {error && (
            <div style={{ ...styles.banner, ...styles.bannerError }}>
              {error}
            </div>
          )}

          {/* ── Controls ── */}
          <div style={styles.section}>
            <label style={styles.label}>Mission Name</label>
            <input
              style={styles.input}
              type="text"
              value={missionName}
              onChange={e => setMissionName(e.target.value)}
              placeholder="Mission 01"
            />
          </div>

          <div style={styles.section}>
            <label style={styles.label}>Camera Preset</label>
            {loadingPresets ? (
              <div style={styles.skeleton}>Loading presets…</div>
            ) : (
              <select
                style={styles.select}
                value={cameraKey}
                onChange={e => setCameraKey(e.target.value)}
              >
                {Object.entries(cameraPresets).map(([key, preset]) => (
                  <option key={key} value={key}>{preset.name}</option>
                ))}
                {Object.keys(cameraPresets).length === 0 && (
                  <option value={cameraKey}>{cameraKey}</option>
                )}
              </select>
            )}
          </div>

          <div style={styles.section}>
            <label style={styles.label}>
              GSD (cm/px)
              <span style={styles.labelValue}>{gsd.toFixed(1)}</span>
            </label>
            <input
              style={styles.rangeInput}
              type="range"
              min={0.1} max={5.0} step={0.1}
              value={gsd}
              onChange={e => setGsd(parseFloat(e.target.value))}
            />
            <div style={styles.rangeLabels}><span>0.1</span><span>5.0</span></div>
          </div>

          <div style={styles.row2col}>
            <div style={styles.section}>
              <label style={styles.label}>Rows</label>
              <input
                style={styles.input}
                type="number"
                min={2} max={50}
                value={numRows}
                onChange={e => setNumRows(parseInt(e.target.value, 10))}
              />
            </div>
            <div style={styles.section}>
              <label style={styles.label}>Speed (m/s)</label>
              <input
                style={styles.input}
                type="number"
                min={1} max={15} step={0.5}
                value={flightSpeed}
                onChange={e => setFlightSpeed(parseFloat(e.target.value))}
              />
            </div>
          </div>

          <div style={styles.row2col}>
            <div style={styles.section}>
              <label style={styles.label}>Zoom Ratio</label>
              <input
                style={styles.input}
                type="number"
                min={1.0} max={16.0} step={0.5}
                value={zoomRatio}
                onChange={e => setZoomRatio(parseFloat(e.target.value))}
              />
            </div>
            <div style={styles.section}>
              <label style={styles.label}>Rotation (°)</label>
              <input
                style={styles.input}
                type="number"
                min={0} max={360}
                value={rotation}
                onChange={e => setRotation(parseFloat(e.target.value))}
              />
            </div>
          </div>

          <div style={styles.row2col}>
            <div style={styles.section}>
              <label style={styles.label}>Gimbal Pitch (°)</label>
              <input
                style={styles.input}
                type="number"
                min={-90} max={0}
                value={gimbalPitch}
                onChange={e => setGimbalPitch(parseFloat(e.target.value))}
              />
            </div>
            <div style={styles.section}>
              <label style={styles.label}>Photo Int. (s)</label>
              <input
                style={styles.input}
                type="number"
                min={0.5} max={10} step={0.5}
                value={photoInterval}
                onChange={e => setPhotoInterval(parseFloat(e.target.value))}
              />
            </div>
          </div>

          <div style={styles.row2col}>
            <div style={styles.section}>
              <label style={styles.label}>Object H. (m)</label>
              <input
                style={styles.input}
                type="number"
                min={0} max={20} step={0.5}
                value={objectHeight}
                onChange={e => setObjectHeight(parseFloat(e.target.value))}
              />
            </div>
            <div style={styles.section}>
              <label style={styles.label}>Aircraft Yaw (°)</label>
              <input
                style={styles.input}
                type="number"
                min={0} max={360}
                value={aircraftYaw}
                onChange={e => setAircraftYaw(parseFloat(e.target.value))}
              />
            </div>
          </div>

          {/* Vertical toggle */}
          <div style={styles.section}>
            <button
              style={{
                ...styles.toggleBtn,
                ...(isVertical ? styles.toggleBtnActive : {}),
              }}
              onClick={() => setIsVertical(v => !v)}
            >
              {isVertical ? 'Vertical Flight' : 'Horizontal Flight'}
            </button>
          </div>

          {/* Action buttons */}
          <div style={styles.actionRow}>
            <button
              style={{
                ...styles.btn,
                ...styles.btnPrimary,
                ...(loadingPreview ? styles.btnDisabled : {}),
              }}
              onClick={handlePreview}
              disabled={loadingPreview}
            >
              {loadingPreview ? 'Generating…' : 'Generate Preview'}
            </button>
            <button
              style={{
                ...styles.btn,
                ...styles.btnSecondary,
                ...(loadingExport ? styles.btnDisabled : {}),
              }}
              onClick={handleExportKmz}
              disabled={loadingExport}
            >
              {loadingExport ? 'Exporting…' : 'Export KMZ'}
            </button>
          </div>

          {/* ── Flight Stats ── */}
          {planResult && (
            <div style={styles.statsCard}>
              <h3 style={styles.statsTitle}>Flight Statistics</h3>
              <div style={styles.statsGrid}>
                <StatItem label="Altitude AGL" value={`${planResult.altitude_agl.toFixed(1)} m`} />
                <StatItem label="Alt. above object" value={`${planResult.altitude_above_object.toFixed(1)} m`} />
                <StatItem label="GSD" value={`${planResult.gsd_cm_px.toFixed(2)} cm/px`} />
                <StatItem label="Distance" value={formatDistance(planResult.estimated_distance_m)} />
                <StatItem label="Duration" value={formatDuration(planResult.estimated_duration_s)} />
                <StatItem label="Photos" value={String(planResult.estimated_photos)} />
                <StatItem label="Waypoints" value={String(planResult.waypoints.length)} />
                <StatItem label="Rows" value={String(planResult.num_rows)} />
                <StatItem label="Speed" value={`${planResult.flight_speed_ms} m/s`} />
                <StatItem label="Camera" value={planResult.camera_name} />
              </div>
            </div>
          )}

          {/* Hint when no boundary */}
          {boundaryCoords.length < 3 && !error && (
            <div style={styles.hint}>
              Use the polygon tool on the map to draw your survey boundary.
            </div>
          )}
        </div>
      </aside>

      {/* ── Map Area ──────────────────────────────────────────────── */}
      <div style={styles.mapWrapper}>
        <MapContainer
          center={[42.5, 12.5]}
          zoom={6}
          style={styles.map}
          scrollWheelZoom
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          <DrawControl onPolygonCreated={handlePolygonCreated} />

          {/* Waypoint markers + row polylines */}
          {planResult &&
            Object.entries(waypointsByRow).map(([rowIdx, wps]) => {
              const color = ROW_COLORS[parseInt(rowIdx, 10) % ROW_COLORS.length]
              const positions = wps.map(
                (wp): [number, number] => [wp.latitude, wp.longitude]
              )
              return (
                <span key={rowIdx}>
                  {/* Row polyline */}
                  <Polyline positions={positions} pathOptions={{ color, weight: 2, opacity: 0.85 }} />
                  {/* Waypoint dots */}
                  {wps.map((wp, i) => (
                    <Marker
                      key={i}
                      position={[wp.latitude, wp.longitude]}
                      icon={waypointIcon(color)}
                    />
                  ))}
                </span>
              )
            })}
        </MapContainer>

        {/* Map legend overlay */}
        {planResult && planResult.waypoints.length > 0 && (
          <div style={styles.mapLegend}>
            <span style={styles.mapLegendTitle}>Rows: {planResult.num_rows}</span>
            <span style={styles.mapLegendSub}>{planResult.waypoints.length} waypoints</span>
          </div>
        )}
      </div>
    </div>
  )
}

// ── StatItem sub-component ────────────────────────────────────────────────────
function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div style={statItemStyles.root}>
      <span style={statItemStyles.label}>{label}</span>
      <span style={statItemStyles.value}>{value}</span>
    </div>
  )
}

const statItemStyles: Record<string, React.CSSProperties> = {
  root: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  label: {
    fontSize: '0.7rem',
    color: '#8a94a6',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  value: {
    fontSize: '0.88rem',
    fontWeight: 600,
    color: '#e2e8f0',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
}

// ── Styles ────────────────────────────────────────────────────────────────────
const styles: Record<string, React.CSSProperties> = {
  pageRoot: {
    display: 'flex',
    height: 'calc(100vh - 48px)',  // full height minus main-content padding
    gap: 0,
    margin: '-24px',               // bleed into main-content padding
    overflow: 'hidden',
  },

  // Sidebar
  sidebar: {
    width: '350px',
    flexShrink: 0,
    background: '#12141f',
    borderRight: '1px solid #2d3142',
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
  },
  sidebarInner: {
    padding: '16px',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  sidebarHeader: {
    marginBottom: '8px',
    paddingBottom: '12px',
    borderBottom: '1px solid #2d3142',
  },
  sidebarTitle: {
    fontSize: '1.1rem',
    fontWeight: 700,
    color: '#e2e8f0',
    margin: 0,
  },
  sidebarSubtitle: {
    fontSize: '0.75rem',
    color: '#8a94a6',
    marginTop: '4px',
  },

  // Section / labels
  section: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    marginBottom: '6px',
  },
  row2col: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '8px',
  },
  label: {
    fontSize: '0.75rem',
    fontWeight: 500,
    color: '#b0bec5',
    display: 'flex',
    justifyContent: 'space-between',
  },
  labelValue: {
    color: '#6c5ce7',
    fontWeight: 700,
  },

  // Inputs
  input: {
    background: '#1a1d27',
    border: '1px solid #2d3142',
    borderRadius: '6px',
    color: '#e2e8f0',
    fontSize: '0.85rem',
    padding: '6px 10px',
    outline: 'none',
    width: '100%',
  },
  select: {
    background: '#1a1d27',
    border: '1px solid #2d3142',
    borderRadius: '6px',
    color: '#e2e8f0',
    fontSize: '0.85rem',
    padding: '6px 10px',
    outline: 'none',
    width: '100%',
    cursor: 'pointer',
  },
  rangeInput: {
    width: '100%',
    accentColor: '#6c5ce7',
    cursor: 'pointer',
  },
  rangeLabels: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: '0.65rem',
    color: '#4a5568',
    marginTop: '-2px',
  },

  // Toggle button
  toggleBtn: {
    width: '100%',
    padding: '8px',
    borderRadius: '6px',
    border: '1px solid #2d3142',
    background: '#1a1d27',
    color: '#8a94a6',
    fontSize: '0.82rem',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.15s',
    textAlign: 'center',
  },
  toggleBtnActive: {
    background: 'rgba(108, 92, 231, 0.2)',
    borderColor: '#6c5ce7',
    color: '#6c5ce7',
  },

  // Action buttons
  actionRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    marginTop: '4px',
    marginBottom: '8px',
  },
  btn: {
    padding: '10px',
    borderRadius: '8px',
    border: 'none',
    fontSize: '0.85rem',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.15s',
    width: '100%',
  },
  btnPrimary: {
    background: '#6c5ce7',
    color: '#fff',
  },
  btnSecondary: {
    background: '#1a1d27',
    color: '#6c5ce7',
    border: '1px solid #6c5ce7',
  },
  btnDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },

  // Banners
  banner: {
    padding: '8px 12px',
    borderRadius: '6px',
    fontSize: '0.78rem',
    marginBottom: '4px',
  },
  bannerError: {
    background: 'rgba(214, 48, 49, 0.15)',
    border: '1px solid rgba(214, 48, 49, 0.4)',
    color: '#ff7675',
  },
  bannerWarning: {
    background: 'rgba(253, 203, 110, 0.1)',
    border: '1px solid rgba(253, 203, 110, 0.3)',
    color: '#fdcb6e',
  },

  // Hint text
  hint: {
    fontSize: '0.75rem',
    color: '#4a5568',
    textAlign: 'center',
    padding: '8px 0',
    fontStyle: 'italic',
  },

  // Skeleton loader
  skeleton: {
    background: '#1a1d27',
    borderRadius: '6px',
    padding: '6px 10px',
    color: '#4a5568',
    fontSize: '0.82rem',
    border: '1px solid #2d3142',
  },

  // Stats card
  statsCard: {
    background: '#1a1d27',
    border: '1px solid #2d3142',
    borderRadius: '8px',
    padding: '12px',
    marginTop: '4px',
  },
  statsTitle: {
    fontSize: '0.8rem',
    fontWeight: 600,
    color: '#6c5ce7',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    marginBottom: '10px',
  },
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '10px',
  },

  // Map
  mapWrapper: {
    flex: 1,
    position: 'relative',
    minWidth: 0,
  },
  map: {
    width: '100%',
    height: '100%',
  },

  // Map legend overlay
  mapLegend: {
    position: 'absolute',
    bottom: '24px',
    right: '10px',
    zIndex: 1000,
    background: 'rgba(18, 20, 31, 0.85)',
    border: '1px solid #2d3142',
    borderRadius: '8px',
    padding: '8px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    backdropFilter: 'blur(4px)',
    pointerEvents: 'none',
  },
  mapLegendTitle: {
    fontSize: '0.82rem',
    fontWeight: 600,
    color: '#e2e8f0',
  },
  mapLegendSub: {
    fontSize: '0.72rem',
    color: '#8a94a6',
  },
}
