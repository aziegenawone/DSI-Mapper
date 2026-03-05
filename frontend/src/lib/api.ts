import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
})

// Types matching backend schemas
export interface Site {
  id: string
  name: string
  capacity_kw: number | null
  address: string | null
  client_name: string | null
}

export interface Flight {
  id: string
  site_id: string
  name: string
  flight_type: 'thermal_inspection' | 'serial_reading' | 'rgb_survey'
  altitude_m: number
  gsd_cm_px: number | null
  overlap_front_pct: number
  overlap_side_pct: number
  estimated_duration_min: number | null
  estimated_photos: number | null
  kmz_url: string | null
}

export interface Inspection {
  id: string
  site_id: string
  inspection_date: string
  operator_name: string | null
  status: 'uploading' | 'processing' | 'completed' | 'validated' | 'failed'
  environmental_conditions: Record<string, unknown> | null
  instruments: Record<string, unknown> | null
}

// API functions
export const sitesApi = {
  list: () => api.get<Site[]>('/sites').then(r => r.data),
  get: (id: string) => api.get<Site>(`/sites/${id}`).then(r => r.data),
  create: (data: Partial<Site>) => api.post<Site>('/sites', data).then(r => r.data),
}

export const flightsApi = {
  list: (siteId?: string) =>
    api.get<Flight[]>('/flights', { params: siteId ? { site_id: siteId } : {} }).then(r => r.data),
  create: (data: Partial<Flight>) => api.post<Flight>('/flights', data).then(r => r.data),
  exportKmz: (id: string) => api.get(`/flights/${id}/kmz`, { responseType: 'blob' }),
}

export const inspectionsApi = {
  list: (siteId?: string) =>
    api.get<Inspection[]>('/inspections', { params: siteId ? { site_id: siteId } : {} }).then(r => r.data),
  create: (data: Partial<Inspection>) => api.post<Inspection>('/inspections', data).then(r => r.data),
}

export default api
