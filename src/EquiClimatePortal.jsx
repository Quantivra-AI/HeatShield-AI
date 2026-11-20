
import React, { useEffect, useMemo, useState } from 'react'
import {
  fetchWorksites,
  fetchZones,
  fetchExposureRecords,
  createExposureRecord,
} from './api'

const getRows = (payload, keys) => {
  if (Array.isArray(payload)) return payload

  for (const key of keys) {
    if (Array.isArray(payload?.[key])) return payload[key]
  }

  return []
}

const getSiteId = site => site.id ?? site.worksite_id

const getZoneId = zone => zone.id ?? zone.zone_id

const formatDate = value => {
  if (!value) return 'Date unavailable'

  const date = new Date(value)

  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleString()
}

const isMeasured = record =>
  record.source === 'onsite_sensor' &&
  record.measured_wbgt_c !== null &&
  record.measured_wbgt_c !== undefined &&
  record.measured_wbgt_c !== '' &&
  Number.isFinite(Number(record.measured_wbgt_c))

const initialSensorForm = {
  zone_id: '',
  measured_wbgt_c: '',
  air_temperature_c: '',
  relative_humidity_pct: '',
  exposure_minutes: '60',
  risk_level: 'moderate',
  notes: '',
}

export default function EquiClimatePortal() {
  const [sites, setSites] = useState([])
  const [zones, setZones] = useState([])
  const [exposures, setExposures] = useState([])
  const [selectedSite, setSelectedSite] = useState('')

  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [saving, setSaving] = useState(false)

  const [error, setError] = useState('')
  const [sensorMessage, setSensorMessage] = useState('')
  const [sensorMessageType, setSensorMessageType] = useState('')

  const [sensorForm, setSensorForm] = useState(initialSensorForm)

  // Load worksites
  useEffect(() => {
    let cancelled = false

    const initialise = async () => {
      setLoading(true)
      setError('')

      try {
        const response = await fetchWorksites()

        const rows = getRows(response, [
          'worksites',
          'items',
          'results',
          'data',
        ])

        if (cancelled) return

        setSites(rows)

        if (rows.length) {
          setSelectedSite(String(getSiteId(rows[0])))
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Unable to load worksites.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    initialise()

    return () => {
      cancelled = true
    }
  }, [])

  // Load zones and exposure records for selected worksite
  useEffect(() => {
    if (!selectedSite) {
      setZones([])
      setExposures([])
      return
    }

    let cancelled = false

    const load = async () => {
      setRefreshing(true)
      setError('')

      try {
        const [zoneResponse, exposureResponse] = await Promise.all([
          fetchZones(selectedSite),
          fetchExposureRecords(selectedSite, 100),
        ])

        if (cancelled) return

        setZones(
          getRows(zoneResponse, [
            'zones',
            'items',
            'results',
            'data',
          ])
        )

        setExposures(
          getRows(exposureResponse, [
            'exposure_records',
            'records',
            'items',
            'results',
            'data',
          ])
        )
      } catch (err) {
        if (!cancelled) {
          setError(
            err.message || 'Unable to load environmental records.'
          )
        }
      } finally {
        if (!cancelled) setRefreshing(false)
      }
    }

    load()

    return () => {
      cancelled = true
    }
  }, [selectedSite])

  const selectedWorksite = sites.find(
    site => String(getSiteId(site)) === String(selectedSite)
  )

  // Only valid onsite sensor measurements count as measured WBGT
  const measuredRecords = useMemo(
    () => exposures.filter(isMeasured),
    [exposures]
  )

  const latestMeasured = useMemo(
    () =>
      [...measuredRecords].sort(
        (a, b) =>
          new Date(b.recorded_at || 0) -
          new Date(a.recorded_at || 0)
      )[0],
    [measuredRecords]
  )

  const weatherEstimateRecords = exposures.filter(
    record => record.source === 'weather_estimate'
  )

  const highRiskRecords = exposures.filter(record =>
    ['high', 'critical'].includes(
      String(record.risk_level || '').toLowerCase()
    )
  )

  // Historical measured WBGT trend
  const measuredTrend = useMemo(() => {
    return [...measuredRecords]
      .filter(record => record.recorded_at)
      .sort(
        (a, b) =>
          new Date(a.recorded_at) - new Date(b.recorded_at)
      )
      .slice(-12)
  }, [measuredRecords])

  const trendValues = measuredTrend.map(record =>
    Number(record.measured_wbgt_c)
  )

  const trendMin = trendValues.length
    ? Math.min(...trendValues)
    : 0

  const trendMax = trendValues.length
    ? Math.max(...trendValues)
    : 1

  const trendRange = Math.max(trendMax - trendMin, 1)

  const trendPoints = trendValues.map((value, index) => ({
    x:
      trendValues.length === 1
        ? 320
        : 30 + (index / (trendValues.length - 1)) * 580,
    y: 175 - ((value - trendMin) / trendRange) * 130,
    value,
  }))

  // Refresh current worksite data
  const refresh = async () => {
    if (!selectedSite) return

    setRefreshing(true)
    setError('')

    try {
      const [zoneResponse, exposureResponse] = await Promise.all([
        fetchZones(selectedSite),
        fetchExposureRecords(selectedSite, 100),
      ])

      setZones(
        getRows(zoneResponse, [
          'zones',
          'items',
          'results',
          'data',
        ])
      )

      setExposures(
        getRows(exposureResponse, [
          'exposure_records',
          'records',
          'items',
          'results',
          'data',
        ])
      )
    } catch (err) {
      setError(err.message || 'Refresh failed.')
    } finally {
      setRefreshing(false)
    }
  }

  // Submit an on-site sensor reading
  const submitSensorReading = async event => {
    event.preventDefault()

    setSensorMessage('')
    setSensorMessageType('')

    if (!selectedSite) {
      setSensorMessage('Select a worksite first.')
      setSensorMessageType('error')
      return
    }

    if (!sensorForm.measured_wbgt_c.trim()) {
      setSensorMessage('Enter a measured WBGT value.')
      setSensorMessageType('error')
      return
    }

    const wbgt = Number(sensorForm.measured_wbgt_c)
    const duration = Number(sensorForm.exposure_minutes)

    const airTemperature =
      sensorForm.air_temperature_c === ''
        ? null
        : Number(sensorForm.air_temperature_c)

    const humidity =
      sensorForm.relative_humidity_pct === ''
        ? null
        : Number(sensorForm.relative_humidity_pct)

    if (!Number.isFinite(wbgt) || wbgt < 0 || wbgt > 60) {
      setSensorMessage('Enter a valid WBGT value between 0 and 60°C.')
      setSensorMessageType('error')
      return
    }

    if (!Number.isInteger(duration) || duration < 1) {
      setSensorMessage('Exposure duration must be at least 1 minute.')
      setSensorMessageType('error')
      return
    }

    if (
      airTemperature !== null &&
      (!Number.isFinite(airTemperature) ||
        airTemperature < -50 ||
        airTemperature > 70)
    ) {
      setSensorMessage('Enter a valid air temperature.')
      setSensorMessageType('error')
      return
    }

    if (
      humidity !== null &&
      (!Number.isFinite(humidity) ||
        humidity < 0 ||
        humidity > 100)
    ) {
      setSensorMessage('Humidity must be between 0 and 100%.')
      setSensorMessageType('error')
      return
    }

    try {
      setSaving(true)

      const payload = {
        worksite_id: Number(selectedSite),
        zone_id: sensorForm.zone_id
          ? Number(sensorForm.zone_id)
          : null,
        exposure_minutes: duration,
        source: 'onsite_sensor',
        risk_level: sensorForm.risk_level,
        measured_wbgt_c: wbgt,
        air_temperature_c: airTemperature,
        relative_humidity_pct: humidity,
        notes: sensorForm.notes.trim() || null,
      }

      await createExposureRecord(payload)

      setSensorMessage(
        'Reading submitted successfully. Environmental history refreshed.'
      )
      setSensorMessageType('success')

      setSensorForm(initialSensorForm)

      const response = await fetchExposureRecords(selectedSite, 100)

      setExposures(
        getRows(response, [
          'exposure_records',
          'records',
          'items',
          'results',
          'data',
        ])
      )
    } catch (err) {
      setSensorMessage(
        err.message || 'Unable to save sensor reading.'
      )
      setSensorMessageType('error')
    } finally {
      setSaving(false)
    }
  }

  const updateSensorField = (field, value) => {
    setSensorForm(previous => ({
      ...previous,
      [field]: value,
    }))
  }

  return (
    <section className="content">
      {/* Header */}
      <div className="welcome-row">
        <div>
          <div className="eyebrow">ENVIRONMENTAL INTELLIGENCE</div>
          <h1>EquiClimate</h1>
          <p className="muted">
            Worksite environmental conditions, zone exposure
            and recorded heat measurements.
          </p>
        </div>

        <button
          className="btn btn-dark"
          onClick={refresh}
          disabled={refreshing || !selectedSite}
        >
          {refreshing ? 'Refreshing...' : 'Refresh data'}
        </button>
      </div>

      {error && (
        <div className="notice">
          <p>{error}</p>
        </div>
      )}

      {/* Worksite selection */}
      <div
        className="card"
        style={{ padding: 20, marginTop: 20 }}
      >
        <div className="eyebrow">WORKSITE SELECTION</div>

        <label
          htmlFor="equiclimate-site"
          style={{
            display: 'block',
            margin: '10px 0 7px',
            fontWeight: 600,
          }}
        >
          Select worksite
        </label>

        <select
          id="equiclimate-site"
          value={selectedSite}
          onChange={event => {
            setSelectedSite(event.target.value)
            setSensorMessage('')
          }}
          style={{
            width: '100%',
            maxWidth: 500,
            padding: 12,
            border: '1px solid #d7ddd3',
            borderRadius: 9,
            font: 'inherit',
          }}
        >
          <option value="">Select a worksite</option>

          {sites.map(site => (
            <option
              key={getSiteId(site)}
              value={String(getSiteId(site))}
            >
              {site.name ||
                site.site_name ||
                `Worksite ${getSiteId(site)}`}
            </option>
          ))}
        </select>

        {selectedWorksite && (
          <p className="muted" style={{ marginBottom: 0 }}>
            {selectedWorksite.city ||
              selectedWorksite.location ||
              'Location unavailable'}
            {' · '}
            {selectedWorksite.industry ||
              selectedWorksite.type ||
              'Industry unavailable'}
          </p>
        )}
      </div>

      {loading || refreshing ? (
        <div
          className="card weather-state"
          style={{ marginTop: 20 }}
        >
          Loading environmental records...
        </div>
      ) : !selectedSite ? (
        <div
          className="card weather-state"
          style={{ marginTop: 20 }}
        >
          No worksite selected. Register a worksite first.
        </div>
      ) : (
        <>
          {/* Dashboard statistics */}
          <div className="stats-grid" style={{ marginTop: 22 }}>
            <div className="stat-card">
              <div className="stat-label">REGISTERED ZONES</div>
              <strong>{zones.length}</strong>
              <small>Zones at selected worksite</small>
            </div>

            <div className="stat-card">
              <div className="stat-label">EXPOSURE RECORDS</div>
              <strong>{exposures.length}</strong>
              <small>Retrieved records</small>
            </div>

            <div className="stat-card">
              <div className="stat-label">MEASURED WBGT</div>
              <strong>
                {latestMeasured
                  ? `${Number(latestMeasured.measured_wbgt_c).toFixed(1)}°C`
                  : '—'}
              </strong>
              <small>
                {latestMeasured
                  ? 'Latest on-site sensor record'
                  : 'No verified on-site measurement'}
              </small>
            </div>

            <div className="stat-card">
              <div className="stat-label">HIGH / CRITICAL RECORDS</div>
              <strong>{highRiskRecords.length}</strong>
              <small>Recorded risk classifications</small>
            </div>

            <div className="stat-card">
              <div className="stat-label">ON-SITE SENSOR RECORDS</div>
              <strong>{measuredRecords.length}</strong>
              <small>Valid measured WBGT records</small>
            </div>

            <div className="stat-card">
              <div className="stat-label">WEATHER ESTIMATES</div>
              <strong>{weatherEstimateRecords.length}</strong>
              <small>Modelled weather-source records</small>
            </div>
          </div>

          {/* Zone overview */}
          <div
            className="section-heading"
            style={{ marginTop: 30 }}
          >
            <div>
              <div className="eyebrow">WORKSITE ENVIRONMENT</div>
              <h2>Zone overview</h2>
            </div>
            <span className="demo-tag">DATABASE RECORDS</span>
          </div>

          <div className="card" style={{ padding: 20 }}>
            {zones.length === 0 ? (
              <div className="weather-state">
                No zones registered for this worksite.
              </div>
            ) : (
              <div className="stats-grid">
                {zones.map((zone, index) => (
                  <div
                    className="stat-card"
                    key={getZoneId(zone) ?? index}
                  >
                    <div className="stat-label">
                      {zone.activity_type || 'WORK ZONE'}
                    </div>

                    <strong style={{ fontSize: 20 }}>
                      {zone.name ||
                        zone.zone_name ||
                        `Zone ${index + 1}`}
                    </strong>

                    <small>
                      Exposure category:{' '}
                      {zone.exposure_category || 'Not specified'}
                    </small>

                    <small>
                      Capacity:{' '}
                      {zone.worker_capacity ?? 'Not specified'}
                    </small>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Historical WBGT trend */}
          <div
            className="section-heading"
            style={{ marginTop: 30 }}
          >
            <div>
              <div className="eyebrow">HISTORICAL SENSOR DATA</div>
              <h2>Measured WBGT trend</h2>
            </div>
            <span className="demo-tag">ON-SITE SENSOR ONLY</span>
          </div>

          <div className="card" style={{ padding: 20 }}>
            {trendPoints.length < 2 ? (
              <div className="weather-state">
                At least two timestamped on-site sensor readings
                are required to display a historical trend.
              </div>
            ) : (
              <>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    marginBottom: 12,
                    flexWrap: 'wrap',
                    gap: 8,
                  }}
                >
                  <span className="muted">
                    Last {trendPoints.length} sensor readings
                  </span>

                  <strong>
                    Latest:{' '}
                    {trendPoints[
                      trendPoints.length - 1
                    ].value.toFixed(1)}
                    °C
                  </strong>
                </div>

                <div style={{ width: '100%', overflow: 'hidden' }}>
                  <svg
                    viewBox="0 0 640 220"
                    role="img"
                    aria-label="Historical measured WBGT trend in degrees Celsius"
                    style={{ width: '100%', height: 'auto' }}
                  >
                    {[45, 110, 175].map(y => (
                      <line
                        key={y}
                        x1="30"
                        y1={y}
                        x2="610"
                        y2={y}
                        stroke="#e3e9e1"
                        strokeDasharray="4 5"
                      />
                    ))}

                    <polyline
                      points={trendPoints
                        .map(point => `${point.x},${point.y}`)
                        .join(' ')}
                      fill="none"
                      stroke="#d97706"
                      strokeWidth="3"
                      strokeLinejoin="round"
                      strokeLinecap="round"
                    />

                    {trendPoints.map((point, index) => (
                      <g key={`${index}-${point.x}`}>
                        <circle
                          cx={point.x}
                          cy={point.y}
                          r="5"
                          fill="#d97706"
                        />
                        <title>
                          {`${point.value.toFixed(1)}°C`}
                        </title>
                      </g>
                    ))}

                    <text
                      x="30"
                      y="205"
                      fontSize="11"
                      fill="currentColor"
                    >
                      Earlier
                    </text>

                    <text
                      x="610"
                      y="205"
                      textAnchor="end"
                      fontSize="11"
                      fill="currentColor"
                    >
                      Latest
                    </text>
                  </svg>
                </div>

                <p className="muted" style={{ fontSize: 12 }}>
                  Historical readings only. This chart does not
                  predict future exposure or determine whether
                  conditions are safe.
                </p>
              </>
            )}
          </div>

          {/* Sensor data ingestion */}
          <div
            className="section-heading"
            style={{ marginTop: 30 }}
          >
            <div>
              <div className="eyebrow">SENSOR DATA MANAGEMENT</div>
              <h2>Record environmental measurement</h2>
            </div>
            <span className="demo-tag">ON-SITE SENSOR</span>
          </div>

          <form
            className="card"
            onSubmit={submitSensorReading}
            style={{ padding: 20 }}
          >
            <p className="muted">
              Submit a verified reading received from an on-site
              sensor. This form records the submitted source label;
              it does not independently authenticate the device.
            </p>

            <div className="stats-grid">
              <label>
                Zone

                <select
                  value={sensorForm.zone_id}
                  onChange={event =>
                    updateSensorField('zone_id', event.target.value)
                  }
                  style={{
                    width: '100%',
                    padding: 11,
                    marginTop: 7,
                  }}
                >
                  <option value="">No specific zone</option>

                  {zones.map((zone, index) => (
                    <option
                      key={getZoneId(zone) ?? index}
                      value={getZoneId(zone)}
                    >
                      {zone.name ||
                        zone.zone_name ||
                        `Zone ${index + 1}`}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Measured WBGT (°C)

                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="60"
                  required
                  value={sensorForm.measured_wbgt_c}
                  onChange={event =>
                    updateSensorField(
                      'measured_wbgt_c',
                      event.target.value
                    )
                  }
                  style={{
                    width: '100%',
                    padding: 11,
                    marginTop: 7,
                  }}
                />
              </label>

              <label>
                Air temperature (°C)

                <input
                  type="number"
                  step="0.1"
                  value={sensorForm.air_temperature_c}
                  onChange={event =>
                    updateSensorField(
                      'air_temperature_c',
                      event.target.value
                    )
                  }
                  style={{
                    width: '100%',
                    padding: 11,
                    marginTop: 7,
                  }}
                />
              </label>

              <label>
                Relative humidity (%)

                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={sensorForm.relative_humidity_pct}
                  onChange={event =>
                    updateSensorField(
                      'relative_humidity_pct',
                      event.target.value
                    )
                  }
                  style={{
                    width: '100%',
                    padding: 11,
                    marginTop: 7,
                  }}
                />
              </label>

              <label>
                Exposure duration (minutes)

                <input
                  type="number"
                  min="1"
                  required
                  value={sensorForm.exposure_minutes}
                  onChange={event =>
                    updateSensorField(
                      'exposure_minutes',
                      event.target.value
                    )
                  }
                  style={{
                    width: '100%',
                    padding: 11,
                    marginTop: 7,
                  }}
                />
              </label>

              <label>
                Recorded risk classification

                <select
                  value={sensorForm.risk_level}
                  onChange={event =>
                    updateSensorField(
                      'risk_level',
                      event.target.value
                    )
                  }
                  style={{
                    width: '100%',
                    padding: 11,
                    marginTop: 7,
                  }}
                >
                  <option value="low">Low</option>
                  <option value="moderate">Moderate</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
              </label>
            </div>

            <label style={{ display: 'block', marginTop: 16 }}>
              Notes

              <textarea
                value={sensorForm.notes}
                onChange={event =>
                  updateSensorField('notes', event.target.value)
                }
                rows={3}
                style={{
                  width: '100%',
                  padding: 11,
                  marginTop: 7,
                }}
              />
            </label>

            {sensorMessage && (
              <div className="notice" style={{ marginTop: 15 }}>
                <p>{sensorMessage}</p>
              </div>
            )}

            <button
              type="submit"
              className="btn btn-dark"
              disabled={saving}
              style={{ marginTop: 16 }}
            >
              {saving ? 'Saving reading...' : 'Save sensor reading'}
            </button>
          </form>

          {/* Exposure history */}
          <div
            className="section-heading"
            style={{ marginTop: 30 }}
          >
            <div>
              <div className="eyebrow">ENVIRONMENTAL MEASUREMENTS</div>
              <h2>Exposure monitoring history</h2>
            </div>
            <span className="demo-tag">SOURCE-IDENTIFIED DATA</span>
          </div>

          <div className="card" style={{ padding: 20 }}>
            {exposures.length === 0 ? (
              <div className="weather-state">
                No exposure records are available for this worksite.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table
                  style={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    fontSize: 13,
                    minWidth: 700,
                  }}
                >
                  <thead>
                    <tr
                      style={{
                        textAlign: 'left',
                        borderBottom: '1px solid #e1e7dd',
                      }}
                    >
                      <th style={{ padding: 12 }}>Recorded at</th>
                      <th style={{ padding: 12 }}>WBGT</th>
                      <th style={{ padding: 12 }}>Data source</th>
                      <th style={{ padding: 12 }}>Risk level</th>
                      <th style={{ padding: 12 }}>Duration</th>
                    </tr>
                  </thead>

                  <tbody>
                    {[...exposures]
                      .sort(
                        (a, b) =>
                          new Date(b.recorded_at || 0) -
                          new Date(a.recorded_at || 0)
                      )
                      .map((record, index) => (
                        <tr
                          key={
                            record.id ??
                            record.record_id ??
                            index
                          }
                          style={{
                            borderBottom: '1px solid #edf0eb',
                          }}
                        >
                          <td style={{ padding: 12 }}>
                            {formatDate(record.recorded_at)}
                          </td>

                          <td style={{ padding: 12 }}>
                            {isMeasured(record)
                              ? `${Number(
                                  record.measured_wbgt_c
                                ).toFixed(1)}°C`
                              : 'Unknown'}
                          </td>

                          <td style={{ padding: 12 }}>
                            {record.source || 'Unspecified'}
                          </td>

                          <td style={{ padding: 12 }}>
                            {record.risk_level || 'Unclassified'}
                          </td>

                          <td style={{ padding: 12 }}>
                            {record.exposure_minutes != null
                              ? `${record.exposure_minutes} min`
                              : 'Unknown'}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Data integrity notice */}
          <div className="notice" style={{ marginTop: 22 }}>
            <p>
              WBGT is shown as a measured value only when the
              record identifies an on-site sensor source and
              contains a valid measurement. Weather-derived
              estimates are not presented as measured WBGT.
              Missing or unavailable readings remain Unknown,
              not Safe. Submitted sensor labels are not proof
              of device authenticity or calibration.
            </p>
          </div>
        </>
      )}
    </section>
  )
}
