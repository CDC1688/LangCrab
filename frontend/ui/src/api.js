const BASE = ''

export async function fetchSessions(filters = {}, offset = 0, limit = 50) {
  const params = new URLSearchParams()
  if (filters.category) params.set('category', filters.category)
  if (filters.subcategory) params.set('subcategory', filters.subcategory)
  if (filters.model) params.set('model', filters.model)
  if (filters.confidence) params.set('confidence', filters.confidence)
  if (filters.has_errors !== null && filters.has_errors !== undefined)
    params.set('has_errors', filters.has_errors)
  if (filters.keyword) params.set('keyword', filters.keyword)
  if (filters.annotation_status) params.set('annotation_status', filters.annotation_status)
  params.set('offset', offset)
  params.set('limit', limit)
  const res = await fetch(`${BASE}/api/sessions?${params}`)
  return res.json()
}

export async function fetchSession(sid) {
  const res = await fetch(`${BASE}/api/sessions/${sid}`)
  return res.json()
}

export async function fetchSessionGraph(sid) {
  const res = await fetch(`${BASE}/api/sessions/${sid}/graph`)
  return res.json()
}

export async function fetchPipelineGraph() {
  const res = await fetch(`${BASE}/api/pipeline/graph`)
  return res.json()
}

export async function fetchSummary() {
  const res = await fetch(`${BASE}/api/summary`)
  return res.json()
}

export async function fetchFilters() {
  const res = await fetch(`${BASE}/api/filters`)
  return res.json()
}

export async function fetchSubcategoryCounts(category) {
  const params = new URLSearchParams()
  if (category) params.set('category', category)
  const res = await fetch(`${BASE}/api/subcategory-counts?${params}`)
  return res.json()
}

export async function fetchAnnotations() {
  const res = await fetch(`${BASE}/api/annotations`)
  return res.json()
}

export async function saveAnnotation(sid, data) {
  const res = await fetch(`${BASE}/api/annotations/${sid}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return res.json()
}

export async function deleteAnnotation(sid) {
  const res = await fetch(`${BASE}/api/annotations/${sid}`, { method: 'DELETE' })
  return res.json()
}

export async function exportAnnotations() {
  const res = await fetch(`${BASE}/api/annotations/export`)
  return res.json()
}

export function createReplaySocket(sid) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return new WebSocket(`${proto}//${host}/ws/replay/${sid}`)
}
