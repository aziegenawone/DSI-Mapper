import { MapContainer, TileLayer } from 'react-leaflet'
import type { ReactNode } from 'react'

interface SiteMapProps {
  center?: [number, number]
  zoom?: number
  children?: ReactNode
}

/**
 * Base map component wrapping Leaflet.
 * Center defaults to Italy (for PV plants).
 */
export default function SiteMap({
  center = [42.5, 12.5],
  zoom = 6,
  children,
}: SiteMapProps) {
  return (
    <MapContainer
      center={center}
      zoom={zoom}
      className="map-container"
      scrollWheelZoom
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {children}
    </MapContainer>
  )
}
