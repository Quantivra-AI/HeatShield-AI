
import React, { useEffect, useMemo, useState } from 'react'
import {
  fetchWorkers,
  fetchWorksites,
  fetchExposureRecords,
  fetchRiskAssessment
} from './api'

export default function AuraHeatPortal() {
  const [workers, setWorkers] = useState([])
  const [sites, setSites] = useState([])
  const [records, setRecords] = useState([])
  const [assessment, setAssessment] = useState(null)
  const [siteId, setSiteId] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [w, s, e] = await Promise.all([
        fetchWorkers(siteId || undefined),
        fetchWorksites(),
        fetchExposureRecords(siteId || undefined, 100)
      ])

      setWorkers(Array.isArray(w) ? w : w.workers || [])
      setSites(Array.isArray(s) ? s : s.worksites || [])
      setRecords(Array.isArray(e) ? e : e.exposure_records || e.records || [])

      if (siteId) {
        try {
          setAssessment(await fetchRiskAssessment(siteId))
        } catch {
          setAssessment(null)
        }
      } else {
        setAssessment(null)
      }
    } catch (err) {
      setError(err.message || 'Unable to load monitoring data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [siteId])

  const filteredRecords = useMemo(() => {
    return records.filter(record => {
      const term = search.toLowerCase()
      return !term || [
        record.worker_code,
        record.risk_level,
        record.source,
        record.notes
      ].some(value => String(value || '').toLowerCase().includes(term))
    })
  }, [records, search])

  const measured = records.filter(
    r => r.source === 'onsite_sensor' &&
      r.measured_wbgt_c !== null &&
      r.measured_wbgt_c !== undefined
  )

  const highRisk = records.filter(
    r => ['high', 'critical'].includes(
      String(r.risk_level || '').toLowerCase()
    )
  )

  const workerCount = new Set(
    records.map(r => r.worker_code).filter(Boolean)
  ).size

  return (
    <section className="content">
      <div className="welcome-row">
        <div>
          <div className="eyebrow">AURAHEAT · WORKER MONITORING</div>
          <h1>Exposure Intelligence</h1>
          <p className="muted">
            Review recorded worker exposure, environmental measurements and risk assessments.
          </p>
        </div>
        <button className="btn btn-dark" onClick={loadData}>
          Refresh monitoring
        </button>
      </div>

      {error && <div className="notice">{error}</div>}

      <div className="card" style={{padding:18, marginBottom:22}}>
        <label>Filter by worksite</label>
        <select value={siteId} onChange={e => setSiteId(e.target.value)}>
          <option value="">All worksites</option>
          {sites.map(site => (
            <option key={site.id} value={site.id}>{site.name}</option>
          ))}
        </select>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">WORKERS WITH RECORDS</div>
          <strong>{workerCount}</strong>
          <small>Distinct worker IDs in exposure records</small>
        </div>

        <div className="stat-card">
          <div className="stat-label">EXPOSURE RECORDS</div>
          <strong>{records.length}</strong>
          <small>Retrieved records</small>
        </div>

        <div className="stat-card">
          <div className="stat-label">HIGH / CRITICAL RECORDS</div>
          <strong>{highRisk.length}</strong>
          <small>Recorded classifications</small>
        </div>

        <div className="stat-card">
          <div className="stat-label">MEASURED WBGT</div>
          <strong>{measured.length}</strong>
          <small>Records explicitly sourced from on-site sensors</small>
        </div>
      </div>

      <div className="section-heading">
        <div>
          <div className="eyebrow">RISK ASSESSMENT</div>
          <h2>Worksite assessment</h2>
        </div>
      </div>

      <div className="card" style={{padding:22, marginBottom:26}}>
        {!siteId ? (
          <p className="muted">Select a worksite to retrieve its risk assessment.</p>
        ) : assessment ? (
          <>
            <h3>{assessment.assessment_type || 'Risk assessment'}</h3>
            <p>Workers assessed: {assessment.workers_assessed ?? '—'}</p>
            {(assessment.results || assessment.assessments || []).map((item, index) => (
              <div className="supervisor-action" key={item.worker_code || index}>
                <div className="priority-dot" />
                <div>
                  <b>{item.worker_code || 'Worker record'}</b>
                  <p>Risk score: {item.risk_score ?? '—'} · Band: {item.risk_band || 'Unknown'}</p>
                  <small>{item.reason || 'No assessment explanation returned.'}</small>
                </div>
              </div>
            ))}
            <div className="notice">
              Assessment outputs are prototype decision-support results, not clinical diagnoses.
            </div>
          </>
        ) : (
          <p className="muted">No assessment result is currently available for this worksite.</p>
        )}
      </div>

      <div className="section-heading">
        <div>
          <div className="eyebrow">EXPOSURE HISTORY</div>
          <h2>Recorded exposure events</h2>
        </div>
      </div>

      <div className="card" style={{padding:20}}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search worker ID, risk band or source..."
          style={{marginBottom:18}}
        />

        {loading ? <p>Loading monitoring records...</p> :
          filteredRecords.length === 0 ? (
            <p>No exposure records found.</p>
          ) : (
            <div style={{overflowX:'auto'}}>
              <table style={{width:'100%',textAlign:'left',borderCollapse:'collapse'}}>
                <thead>
                  <tr>
                    <th style={{padding:12}}>Worker</th>
                    <th style={{padding:12}}>Risk band</th>
                    <th style={{padding:12}}>Duration</th>
                    <th style={{padding:12}}>WBGT</th>
                    <th style={{padding:12}}>Source</th>
                    <th style={{padding:12}}>Recorded</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRecords.map((record, index) => (
                    <tr key={record.id || index}>
                      <td style={{padding:12}}>{record.worker_code || 'Site-level record'}</td>
                      <td style={{padding:12}}>{record.risk_level || 'Unknown'}</td>
                      <td style={{padding:12}}>{record.duration_minutes ?? '—'} min</td>
                      <td style={{padding:12}}>
                        {record.source === 'onsite_sensor' &&
                        record.measured_wbgt_c != null
                          ? `${Number(record.measured_wbgt_c).toFixed(1)}°C`
                          : 'Not measured'}
                      </td>
                      <td style={{padding:12}}>{record.source || 'Unknown'}</td>
                      <td style={{padding:12}}>
                        {record.recorded_at
                          ? new Date(record.recorded_at).toLocaleString()
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </div>

      <div className="notice" style={{marginTop:20}}>
        Exposure records are not equivalent to live wearable vitals. Missing measurements
        remain unknown; weather estimates are never displayed as measured WBGT.
      </div>
    </section>
  )
}
