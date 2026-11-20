
import React, { useEffect, useState } from 'react'
import {
  fetchWorksites,
  createWorksite,
  updateWorksite,
  deleteWorksite,
  fetchZones,
  createZone
} from './api'

export default function WorksitePortal() {
  const [sites, setSites] = useState([])
  const [zones, setZones] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [showSiteForm, setShowSiteForm] = useState(false)
  const [showZoneForm, setShowZoneForm] = useState(false)
  const [selected, setSelected] = useState(null)
  const [editing, setEditing] = useState(null)

  const emptySite = {
    name: '',
    city: '',
    industry: 'construction',
    worker_count: 0
  }

  const [siteForm, setSiteForm] = useState(emptySite)
  const [zoneForm, setZoneForm] = useState({
    worksite_id: '',
    name: '',
    activity: '',
    exposure_level: 'moderate',
    capacity: 0
  })

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [s, z] = await Promise.all([
        fetchWorksites(),
        fetchZones()
      ])
      setSites(Array.isArray(s) ? s : s.worksites || [])
      setZones(Array.isArray(z) ? z : z.zones || [])
    } catch (e) {
      setError(e.message || 'Could not load worksites.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  function startEdit(site) {
    setEditing(site.id)
    setSiteForm({
      name: site.name || '',
      city: site.city || '',
      industry: site.industry || 'construction',
      worker_count: site.worker_count || 0
    })
    setShowSiteForm(true)
  }

  async function saveSite(e) {
    e.preventDefault()
    setError('')
    setMessage('')
    try {
      const payload = {
        ...siteForm,
        worker_count: Number(siteForm.worker_count)
      }
      if (editing) {
        await updateWorksite(editing, payload)
        setMessage('Worksite updated.')
      } else {
        await createWorksite(payload)
        setMessage('Worksite created.')
      }
      setShowSiteForm(false)
      setEditing(null)
      setSiteForm(emptySite)
      await loadData()
    } catch (e) {
      setError(e.message || 'Unable to save worksite.')
    }
  }

  async function removeSite(id) {
    if (!window.confirm('Delete this worksite?')) return
    try {
      await deleteWorksite(id)
      setSelected(null)
      setMessage('Worksite deleted.')
      await loadData()
    } catch (e) {
      setError(e.message || 'Unable to delete worksite.')
    }
  }

  async function saveZone(e) {
    e.preventDefault()
    setError('')
    try {
      await createZone({
        ...zoneForm,
        worksite_id: Number(zoneForm.worksite_id),
        capacity: Number(zoneForm.capacity)
      })
      setMessage('Zone created.')
      setShowZoneForm(false)
      setZoneForm({
        worksite_id: selected?.id || '',
        name: '',
        activity: '',
        exposure_level: 'moderate',
        capacity: 0
      })
      await loadData()
    } catch (e) {
      setError(e.message || 'Unable to create zone.')
    }
  }

  const selectedZones = zones.filter(
    z => String(z.worksite_id) === String(selected?.id)
  )

  return (
    <section className="content">
      <div className="welcome-row">
        <div>
          <div className="eyebrow">SITE OPERATIONS</div>
          <h1>Worksite Management</h1>
          <p className="muted">
            Manage construction sites, operational areas and zone assignments.
          </p>
        </div>
        <button className="btn btn-dark" onClick={() => {
          setEditing(null)
          setSiteForm(emptySite)
          setShowSiteForm(!showSiteForm)
        }}>
          + Add worksite
        </button>
      </div>

      {error && <div className="notice">{error}</div>}
      {message && <div className="notice">{message}</div>}

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">REGISTERED SITES</div>
          <strong>{sites.length}</strong>
          <small>Sites in the platform</small>
        </div>
        <div className="stat-card">
          <div className="stat-label">OPERATIONAL ZONES</div>
          <strong>{zones.length}</strong>
          <small>Configured site zones</small>
        </div>
        <div className="stat-card">
          <div className="stat-label">HIGH EXPOSURE ZONES</div>
          <strong>{zones.filter(z =>
            String(z.exposure_level || z.exposure || '').toLowerCase() === 'high'
          ).length}</strong>
          <small>Require appropriate controls</small>
        </div>
      </div>

      {showSiteForm && (
        <div className="card" style={{padding:24, marginBottom:24}}>
          <h2>{editing ? 'Edit worksite' : 'Register new worksite'}</h2>
          <form onSubmit={saveSite}>
            <div className="form-grid">
              <div>
                <label>Worksite name</label>
                <input required value={siteForm.name}
                  onChange={e => setSiteForm({...siteForm,name:e.target.value})}/>
              </div>
              <div>
                <label>City</label>
                <input required value={siteForm.city}
                  onChange={e => setSiteForm({...siteForm,city:e.target.value})}/>
              </div>
              <div>
                <label>Industry</label>
                <select value={siteForm.industry}
                  onChange={e => setSiteForm({...siteForm,industry:e.target.value})}>
                  <option value="construction">Construction</option>
                  <option value="manufacturing">Manufacturing</option>
                  <option value="logistics">Logistics</option>
                  <option value="utilities">Utilities</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label>Expected workforce</label>
                <input type="number" min="0" value={siteForm.worker_count}
                  onChange={e => setSiteForm({...siteForm,worker_count:e.target.value})}/>
              </div>
            </div>
            <button className="btn btn-dark" type="submit">
              {editing ? 'Update worksite' : 'Save worksite'}
            </button>
          </form>
        </div>
      )}

      <div className="section-heading">
        <div>
          <div className="eyebrow">WORKSITE DIRECTORY</div>
          <h2>Registered locations</h2>
        </div>
        <button className="btn btn-dark" onClick={loadData}>Refresh</button>
      </div>

      {loading ? <p>Loading sites...</p> : (
        <div className="grid" style={{
          display:'grid',
          gridTemplateColumns:'repeat(auto-fit,minmax(260px,1fr))',
          gap:18
        }}>
          {sites.map(site => {
            const count = zones.filter(
              z => String(z.worksite_id) === String(site.id)
            ).length

            return (
              <article className="card" key={site.id} style={{padding:22}}>
                <div className="eyebrow">WORKSITE #{site.id}</div>
                <h2>{site.name}</h2>
                <p className="muted">{site.city || site.location || 'Location not specified'}</p>
                <div className="stats-grid">
                  <div>
                    <strong>{count}</strong>
                    <small>Zones</small>
                  </div>
                  <div>
                    <strong>{site.worker_count ?? 0}</strong>
                    <small>Expected workers</small>
                  </div>
                </div>
                <div style={{display:'flex',gap:8,flexWrap:'wrap',marginTop:18}}>
                  <button className="btn btn-dark" onClick={() => setSelected(site)}>
                    View details
                  </button>
                  <button className="btn btn-dark" onClick={() => startEdit(site)}>
                    Edit
                  </button>
                  <button className="btn" onClick={() => removeSite(site.id)}>
                    Delete
                  </button>
                </div>
              </article>
            )
          })}
        </div>
      )}

      {selected && (
        <div className="card" style={{padding:24,marginTop:28}}>
          <div className="welcome-row">
            <div>
              <div className="eyebrow">WORKSITE DETAILS</div>
              <h2>{selected.name}</h2>
              <p className="muted">{selected.city || selected.location}</p>
            </div>
            <button className="btn" onClick={() => setSelected(null)}>Close</button>
          </div>

          <div className="section-heading">
            <h3>Operational zones</h3>
            <button className="btn btn-dark" onClick={() => {
              setZoneForm({
                worksite_id: selected.id,
                name:'',
                activity:'',
                exposure_level:'moderate',
                capacity:0
              })
              setShowZoneForm(true)
            }}>+ Add zone</button>
          </div>

          {selectedZones.map(zone => (
            <div className="supervisor-action" key={zone.id}>
              <div className="priority-dot"/>
              <div>
                <b>{zone.name}</b>
                <p>{zone.activity || 'Activity not specified'}</p>
                <small>
                  {zone.exposure_level || zone.exposure || 'Unknown'} exposure · Capacity {zone.capacity ?? '—'}
                </small>
              </div>
            </div>
          ))}

          {selectedZones.length === 0 && <p>No zones configured for this site.</p>}
        </div>
      )}

      {showZoneForm && selected && (
        <div className="card" style={{padding:24,marginTop:20}}>
          <h3>Add operational zone</h3>
          <form onSubmit={saveZone}>
            <div className="form-grid">
              <div>
                <label>Zone name</label>
                <input required value={zoneForm.name}
                  onChange={e => setZoneForm({...zoneForm,name:e.target.value})}/>
              </div>
              <div>
                <label>Activity</label>
                <input value={zoneForm.activity}
                  onChange={e => setZoneForm({...zoneForm,activity:e.target.value})}/>
              </div>
              <div>
                <label>Exposure classification</label>
                <select value={zoneForm.exposure_level}
                  onChange={e => setZoneForm({...zoneForm,exposure_level:e.target.value})}>
                  <option value="low">Low</option>
                  <option value="moderate">Moderate</option>
                  <option value="high">High</option>
                </select>
              </div>
              <div>
                <label>Capacity</label>
                <input type="number" min="0" value={zoneForm.capacity}
                  onChange={e => setZoneForm({...zoneForm,capacity:e.target.value})}/>
              </div>
            </div>
            <button className="btn btn-dark" type="submit">Save zone</button>
            <button className="btn" type="button" onClick={() => setShowZoneForm(false)}>Cancel</button>
          </form>
        </div>
      )}
    </section>
  )
}
