const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function request(path, options = {}) {
  const token = localStorage.getItem('heatshield_access_token')
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `API request failed (${response.status})`)
  }

  if (response.status === 204) return null
  return response.json()
}

export function fetchWeather(city = 'islamabad') {
  return request(`/api/weather/${encodeURIComponent(city)}`)
}

export function fetchWorksites() {
  return request('/api/worksites')
}

export function createWorksite(payload) {
  return request('/api/worksites', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateWorksite(id, payload) {
  return request(`/api/worksites/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteWorksite(id) {
  return request(`/api/worksites/${id}`, { method: 'DELETE' })
}

export function fetchZones(worksiteId) {
  const query = worksiteId ? `?worksite_id=${encodeURIComponent(worksiteId)}` : ''
  return request(`/api/zones${query}`)
}

export function createZone(payload) {
  return request('/api/zones', { method: 'POST', body: JSON.stringify(payload) })
}

export function fetchWorkers(worksiteId) {
  const query = worksiteId ? `?worksite_id=${encodeURIComponent(worksiteId)}` : ''
  return request(`/api/workers${query}`)
}

export function createWorker(payload) {
  return request('/api/workers', { method: 'POST', body: JSON.stringify(payload) })
}

export function fetchExposureRecords(worksiteId, limit = 100) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (worksiteId) params.set('worksite_id', String(worksiteId))
  return request(`/api/exposure-records?${params.toString()}`)
}

export function createExposureRecord(payload) {
  return request('/api/exposure-records', { method: 'POST', body: JSON.stringify(payload) })
}

export function fetchInterventions(worksiteId) {
  const query = worksiteId ? `?worksite_id=${encodeURIComponent(worksiteId)}` : ''
  return request(`/api/interventions${query}`)
}

export function createIntervention(payload) {
  return request('/api/interventions', { method: 'POST', body: JSON.stringify(payload) })
}

export function fetchDashboardSummary() {
  return request('/api/dashboard/summary')
}

export function fetchBioTwinKnowledgeBaseStatus() {
  return request('/api/biotwin/knowledge-base/status')
}

export function askBioTwinResearch(question, top_k = 8) {
  return request('/api/biotwin/agent/ask', {
    method: 'POST',
    body: JSON.stringify({ question, top_k }),
  })
}

export function fetchChronicHealthCatalog() {
  return request('/api/biotwin/chronic-health/catalog')
}

export function askChronicHealth(payload) {
  return request('/api/biotwin/chronic-health/ask', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchKnowledgeBaseStatus() {
  return request('/api/biotwin/knowledge-base/status')
}

export function fetchMeshStatus(worksiteId) {
  if (!worksiteId) return Promise.resolve({ status: 'unknown', notice: 'No worksite selected.' })
  return request(`/api/mesh/status?worksite_id=${encodeURIComponent(worksiteId)}`)
}

export function fetchOfflineAlerts(worksiteId) {
  if (!worksiteId) return Promise.resolve({ alerts: [], pending_alerts: 0, notice: 'Select a registered worksite to view queued alerts.' })
  return request(`/api/mesh/offline-alerts?worksite_id=${encodeURIComponent(worksiteId)}`)
}


export function fetchRiskAssessment(worksiteId) {
  return request(`/api/risk/assessment?worksite_id=${encodeURIComponent(worksiteId)}`)
}

export function fetchShiftRotation(worksiteId) {
  return request(`/api/optimization/shift-rotation?worksite_id=${encodeURIComponent(worksiteId)}`)
}

export function updateInterventionStatus(id, status) {
  return request(`/api/interventions/${encodeURIComponent(id)}/status?status=${encodeURIComponent(status)}`, { method: 'PATCH' })
}

export function syncOfflineAlerts(worksiteId) {
  return request(`/api/mesh/sync?worksite_id=${encodeURIComponent(worksiteId)}`, { method: 'POST' })
}

export function createOfflineAlert(payload) {
  return request('/api/mesh/offline-alerts', { method: 'POST', body: JSON.stringify(payload) })
}


export function loginUser(email, password) {
  return request('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
}
export function fetchCurrentUser() { return request('/api/auth/me') }
export function fetchUsers() { return request('/api/auth/users') }
export function createUser(payload) { return request('/api/auth/users', { method: 'POST', body: JSON.stringify(payload) }) }


export function fetchWorkerHealthDemo(worksiteId) {
  const query = worksiteId ? `?worksite_id=${encodeURIComponent(worksiteId)}` : ''
  return request(`/api/biotwin/worker-health-demo${query}`)
}

export function fetchWorkerVitals(worksiteId) {
  return request(`/api/biotwin/vitals?worksite_id=${encodeURIComponent(worksiteId)}`)
}

export function createWorkerVitals(payload) {
  return request('/api/biotwin/vitals', { method: 'POST', body: JSON.stringify(payload) })
}

export function fetchVitalsModelStatus() {
  return request('/api/biotwin/vitals/model-status')
}
