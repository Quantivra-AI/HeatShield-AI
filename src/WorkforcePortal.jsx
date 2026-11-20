
import React, { useEffect, useState } from 'react'
import { fetchWorkers, fetchWorksites, fetchZones, createWorker } from './api'

export default function WorkforcePortal() {
  const [workers, setWorkers] = useState([])
  const [sites, setSites] = useState([])
  const [zones, setZones] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [search, setSearch] = useState('')
  const [showForm, setShowForm] = useState(false)

  const [form, setForm] = useState({
    worksite_id: '',
    zone_id: '',
    worker_code: '',
    role: 'Construction Worker'
  })

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [w, s, z] = await Promise.all([
        fetchWorkers(),
        fetchWorksites(),
        fetchZones()
      ])
      setWorkers(Array.isArray(w) ? w : w.workers || [])
      setSites(Array.isArray(s) ? s : s.worksites || [])
      setZones(Array.isArray(z) ? z : z.zones || [])
    } catch (e) {
      setError(e.message || 'Unable to load workforce data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await createWorker({
        ...form,
        worksite_id: Number(form.worksite_id),
        zone_id: form.zone_id ? Number(form.zone_id) : null
      })
      setMessage('Worker registered successfully.')
      setForm({
        worksite_id: '',
        zone_id: '',
        worker_code: '',
        role: 'Construction Worker'
      })
      setShowForm(false)
      await loadData()
    } catch (e) {
      setError(e.message || 'Worker registration failed.')
    } finally {
      setSaving(false)
    }
  }

  const filtered = workers.filter(w =>
    `${w.worker_code || ''} ${w.role || ''}`
      .toLowerCase().includes(search.toLowerCase())
  )

  const active = workers.filter(w => w.active !== false && w.active !== 0)

  return (
    <section className="content">
      <div className="welcome-row">
        <div>
          <div className="eyebrow">PEOPLE OPERATIONS</div>
          <h1>Workforce Management</h1>
          <p className="muted">
            Manage worker records, worksite assignments and workforce registration.
          </p>
        </div>
        <button className="btn btn-dark" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Close registration' : '+ Register worker'}
        </button>
      </div>

      {error && <div className="notice">{error}</div>}
      {message && <div className="notice">{message}</div>}

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">REGISTERED WORKERS</div>
          <strong>{workers.length}</strong>
          <small>Worker records in the platform</small>
        </div>
        <div className="stat-card">
          <div className="stat-label">ACTIVE WORKERS</div>
          <strong>{active.length}</strong>
          <small>Records currently marked active</small>
        </div>
        <div className="stat-card">
          <div className="stat-label">REGISTERED WORKSITES</div>
          <strong>{sites.length}</strong>
          <small>Available worksite assignments</small>
        </div>
      </div>

      {showForm && (
        <div className="card" style={{padding:24, marginBottom:24}}>
          <div className="eyebrow">NEW WORKER RECORD</div>
          <h2>Register a worker</h2>
          <form onSubmit={handleSubmit}>
            <div className="form-grid">
              <div>
                <label>Worker ID / Code</label>
                <input required value={form.worker_code}
                  onChange={e => setForm({...form, worker_code:e.target.value})}
                  placeholder="e.g. AD-WRK-001" />
              </div>
              <div>
                <label>Job role</label>
                <input required value={form.role}
                  onChange={e => setForm({...form, role:e.target.value})}
                  placeholder="Construction Worker" />
              </div>
              <div>
                <label>Worksite</label>
                <select required value={form.worksite_id}
                  onChange={e => setForm({...form,worksite_id:e.target.value,zone_id:''})}>
                  <option value="">Select worksite</option>
                  {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
              <div>
                <label>Assigned zone</label>
                <select value={form.zone_id}
                  onChange={e => setForm({...form,zone_id:e.target.value})}>
                  <option value="">Not assigned</option>
                  {zones.filter(z => !form.worksite_id || String(z.worksite_id) === String(form.worksite_id))
                    .map(z => <option key={z.id} value={z.id}>{z.name}</option>)}
                </select>
              </div>
            </div>
            <button className="btn btn-dark" type="submit" disabled={saving}>
              {saving ? 'Registering…' : 'Save worker record'}
            </button>
          </form>
        </div>
      )}

      <div className="section-heading">
        <div>
          <div className="eyebrow">WORKFORCE DIRECTORY</div>
          <h2>Registered workers</h2>
        </div>
        <button className="btn btn-dark" onClick={loadData}>Refresh</button>
      </div>

      <div className="card" style={{padding:20}}>
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search by worker ID or role…" style={{marginBottom:18}} />

        {loading ? <p>Loading workforce records…</p> :
          filtered.length === 0 ? <p>No matching worker records found.</p> :
          <div style={{overflowX:'auto'}}>
            <table style={{width:'100%',textAlign:'left',borderCollapse:'collapse'}}>
              <thead>
                <tr>
                  <th style={{padding:12}}>Worker ID</th>
                  <th style={{padding:12}}>Role</th>
                  <th style={{padding:12}}>Worksite</th>
                  <th style={{padding:12}}>Zone</th>
                  <th style={{padding:12}}>Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(w => (
                  <tr key={w.id}>
                    <td style={{padding:12}}>{w.worker_code}</td>
                    <td style={{padding:12}}>{w.role}</td>
                    <td style={{padding:12}}>
                      {sites.find(s => String(s.id) === String(w.worksite_id))?.name || `Site ${w.worksite_id}`}
                    </td>
                    <td style={{padding:12}}>
                      {zones.find(z => String(z.id) === String(w.zone_id))?.name || 'Unassigned'}
                    </td>
                    <td style={{padding:12}}>
                      {w.active === false || w.active === 0 ? 'Inactive' : 'Active'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        }
      </div>
    </section>
  )
}