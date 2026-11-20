import React, { useState } from 'react'
import { assessRisk } from './risk'
import AdminUsers from './AdminUsers'
import WorkforcePortal from './WorkforcePortal'
import WorksitePortal from './WorksitePortal'
import AuraHeatPortal from './AuraHeatPortal'
import EquiClimatePortal from './EquiClimatePortal'

import {

  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, Bell, Check, ChevronDown,

  ClipboardCheck, CloudSun, Droplets, HardHat, HeartPulse, Home, MapPin, Menu,

  Moon, ShieldCheck, Sun, Thermometer, Users, Wind, X, Clock3, Info, Smartphone,

  Building2, ChartNoAxesCombined, Settings, CircleHelp, BookOpen, Wifi

} from 'lucide-react'

import ModuleWorkspace from './ModuleWorkspace'

import {
  fetchWeather,
  fetchWorksites,
  fetchWorkers,
  fetchZones,
  fetchExposureRecords,
  fetchInterventions,
  fetchDashboardSummary,
  askBioTwinResearch,
  loginUser,
  fetchCurrentUser,
} from './api'




const LOGIN_WORKSPACES = {
  overview: { label: 'Command Center', roles: ['admin', 'executive', 'supervisor'] },
  worker: { label: 'Worker Portal', roles: ['admin', 'worker'] },
  auraheat: { label: 'AuraHeat Monitoring', roles: ['admin', 'supervisor', 'health_safety'] },
  equiclimate: { label: 'EquiClimate', roles: ['admin', 'supervisor', 'health_safety'] },
  biotwin: { label: 'BioTwin Research', roles: ['admin', 'researcher'] },
  mesh: { label: 'BioShield Mesh', roles: ['admin', 'supervisor'] },
  preventive: { label: 'Preventive Care', roles: ['admin', 'supervisor', 'health_safety'] },
  analytics: { label: 'Analytics & Reports', roles: ['admin', 'executive', 'supervisor'] },
  'admin-users': { label: 'User Management', roles: ['admin'] },
  workforce: { label: 'Workforce Management', roles: ['admin', 'supervisor'] },
  worksites: { label: 'Worksite Management', roles: ['admin', 'supervisor'] },
}

function requestedLoginWorkspace() {
  const segments = window.location.pathname.split('/').filter(Boolean)
  if (segments[0] !== 'login' || !segments[1]) return null
  return LOGIN_WORKSPACES[segments[1]] ? segments[1] : null
}

const clothingOptions = [

  { label: 'Normal work clothing', value: 0 },

  { label: 'SMS coveralls', value: 0.5 },

  { label: 'Polyolefin coveralls', value: 1 },

  { label: 'Double-layer clothing', value: 3 },

  { label: 'Vapor-barrier coveralls', value: 11 },

]





function ResearchMarkdown({ content = '' }) {
  const lines = String(content).replace(/\r/g, '').replace(/\[(?:E|e)\d+\]/g, '').replace(/\bEVIDENCE[_ ]ID[: ]*\w+/gi, '').split('\n')
  const blocks = []
  let paragraph = []
  let list = []
  let table = []

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ type: 'p', text: paragraph.join(' ') })
      paragraph = []
    }
  }
  const flushList = () => {
    if (list.length) {
      blocks.push({ type: 'list', items: list })
      list = []
    }
  }
  const flushTable = () => {
    if (table.length) {
      blocks.push({ type: 'table', rows: table })
      table = []
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) {
      flushParagraph(); flushList(); flushTable()
      continue
    }
    if (/^\|.*\|$/.test(line)) {
      flushParagraph(); flushList()
      if (/^\|[\s|:-]+\|$/.test(line)) continue
      table.push(line.split('|').slice(1, -1).map(cell => cell.trim()))
      continue
    }
    flushTable()
    if (/^#{1,4}\s/.test(line)) {
      flushParagraph(); flushList()
      blocks.push({ type: 'heading', level: Math.min(line.match(/^#+/)[0].length, 3), text: line.replace(/^#{1,4}\s+/, '') })
    } else if (/^[-*]\s+/.test(line)) {
      flushParagraph()
      list.push(line.replace(/^[-*]\s+/, ''))
    } else if (/^\d+\.\s+/.test(line)) {
      flushParagraph()
      list.push(line.replace(/^\d+\.\s+/, ''))
    } else {
      flushList()
      paragraph.push(line)
    }
  }
  flushParagraph(); flushList(); flushTable()

  const inline = (text) => text
    .split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
    .map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) return <strong key={i}>{part.slice(2, -2)}</strong>
      if (part.startsWith('`') && part.endsWith('`')) return <code key={i}>{part.slice(1, -1)}</code>
      return part
    })

  return (
    <div className="research-markdown">
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          const Tag = block.level === 1 ? 'h4' : block.level === 2 ? 'h5' : 'h6'
          return <Tag key={index}>{inline(block.text)}</Tag>
        }
        if (block.type === 'list') return <ul key={index}>{block.items.map((item, i) => <li key={i}>{inline(item)}</li>)}</ul>
        if (block.type === 'table') return (
          <div className="research-table-wrap" key={index}>
            <table className="research-table">
              <thead><tr>{block.rows[0]?.map((cell, i) => <th key={i}>{inline(cell)}</th>)}</tr></thead>
              <tbody>{block.rows.slice(1).map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{inline(cell)}</td>)}</tr>)}</tbody>
            </table>
          </div>
        )
        return <p key={index}>{inline(block.text)}</p>
      })}
    </div>
  )
}

function ResearchEvidenceCard({ item }) {
  const [expanded, setExpanded] = useState(false)
  const title = String(item.title || item.source || 'Research source').replace(/\s+/g, ' ').trim()
  const organization = String(item.organization || item.source || 'Indexed source').replace(/\s+/g, ' ').trim()
  const excerpt = String(item.content || '').replace(/\[(?:E|e)\d+\]/g, '').replace(/\s+/g, ' ').trim()
  const summary = excerpt.length > 190 ? `${excerpt.slice(0, 187).replace(/\s+\S*$/, '')}…` : excerpt
  return (
    <article className="research-source-row">
      <div className="research-source-row-main">
        <div className="research-source-copy"><h4>{title}</h4><p>{organization}{item.page_start ? ` · Page ${item.page_start}` : ''}</p></div>
        <button className="research-expand" type="button" onClick={() => setExpanded(value => !value)} aria-expanded={expanded}>
          {expanded ? 'Less' : 'Details'} <ChevronDown size={14} style={{ transform: expanded ? 'rotate(180deg)' : 'none' }}/>
        </button>
      </div>
      <p className="research-source-summary">{summary || 'Source indexed; excerpt not available.'}</p>
      {expanded && <div className="research-source-detail"><ResearchMarkdown content={excerpt}/></div>}
      {item.source_url && <a className="research-source-link" href={item.source_url} target="_blank" rel="noreferrer">Open original source <ArrowRight size={13}/></a>}
    </article>
  )
}

function AgentExecutionTrace({ trace, validation }) {
  if (!trace) return null
  const steps = Array.isArray(trace.execution) ? trace.execution : []
  const statusLabel = status => status === 'passed' ? 'Passed' : status === 'completed' ? 'Completed' : status || 'Unknown'
  return (
    <section className="biotwin-agent-trace" style={{ marginTop: '20px', padding: '18px', border: '1px solid #dce4d8', borderRadius: '12px', background: '#f8faf6' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
        <div>
          <span className="biotwin-kicker">EXPLAINABLE AI</span>
          <h4 style={{ margin: '5px 0 0' }}>{trace.agent || 'BioTwin Research Agent'}</h4>
        </div>
        <span className={`biotwin-generation-state ${validation?.status === 'valid_ids' ? 'is-live' : 'is-fallback'}`}>
          {validation?.status === 'valid_ids' ? 'Citation IDs validated' : 'Citation check needs review'}
        </span>
      </div>
      {trace.intent && <p style={{ margin: '12px 0 8px', color: '#536052', fontSize: '13px' }}>Intent: <b>{String(trace.intent).replaceAll('_', ' ')}</b></p>}
      {steps.length > 0 && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(175px, 1fr))', gap: '9px', marginTop: '12px' }}>
        {steps.map((step, index) => (
          <div key={`${step.step || 'step'}-${index}`} style={{ padding: '11px 12px', border: '1px solid #e1e7dd', borderRadius: '9px', background: '#fff' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
              <b style={{ fontSize: '12px', textTransform: 'capitalize' }}>{String(step.step || 'Agent step').replaceAll('_', ' ')}</b>
              <span style={{ fontSize: '10px', fontWeight: 700, color: step.status === 'passed' || step.status === 'completed' ? '#38734a' : '#946a2c' }}>{statusLabel(step.status)}</span>
            </div>
            {step.evidence_items_returned !== undefined && <small style={{ display: 'block', marginTop: '5px', color: '#687568' }}>{step.evidence_items_returned} evidence items returned</small>}
            {Array.isArray(step.validated_ids) && <small style={{ display: 'block', marginTop: '5px', color: '#687568' }}>{step.validated_ids.length} citation IDs checked</small>}
          </div>
        ))}
      </div>}
      {trace.guardrail && <div style={{ marginTop: '13px', padding: '11px 12px', borderRadius: '8px', background: '#fff4e8', color: '#75512a', fontSize: '12px' }}><b>Safety boundary:</b> {trace.guardrail}</div>}
      {validation?.semantic_entailment === 'not_automatically_verified' && <p style={{ margin: '10px 0 0', color: '#687568', fontSize: '11px' }}>Citation IDs are checked against retrieved evidence. Whether each citation fully supports its associated sentence is not automatically verified.</p>}
    </section>
  )
}

function ResearchInsightDashboard({ result }) {
  const evidence = result?.evidence || []
  const core = evidence.find(item => /core body temperature/i.test(item.title))
  const mean = evidence.find(item => /mean body temperature/i.test(item.title))
  const prospie = evidence.find(item => /prospie|ml experiment/i.test(`${item.title} ${item.source}`))
  const overview = evidence.find(item => /study overview/i.test(item.title))
  const metric = item => {
    const content = item?.content || ''
    const read = label => {
      const match = content.match(new RegExp(`${label}\\s*:?\\s*(-?\\d+(?:\\.\\d+)?)`, 'i'))
      return match ? Number(match[1]) : null
    }
    return { before: read('Before acclimation mean'), after: read('After acclimation mean'), change: read('Mean change'), p: read('Adjusted p-value') }
  }
  const coreValues = metric(core)
  const meanValues = metric(mean)
  const participantsMatch = String(overview?.content || core?.content || '').match(/Participants?:\s*(\d+)/i)
  const sampleMatch = String(prospie?.content || '').match(/Participant-condition samples?:\s*(\d+)/i)
  const outerMatch = String(prospie?.content || '').match(/Outer folds?:\s*(\d+)/i)
  const innerMatch = String(prospie?.content || '').match(/Inner folds?:\s*(\d+)/i)
  const uniqueMatch = String(prospie?.content || '').match(/Unique participants?:\s*(\d+)/i)
  const Finding = ({ title, values }) => (
    <article className="biotwin-finding-card">
      <div className="biotwin-finding-heading"><span>{title}</span><span>PRE / POST</span></div>
      {values.before !== null && values.after !== null ? <div className="biotwin-comparison">
        <div><small>Before</small><strong>{values.before.toFixed(2)}°C</strong></div>
        <div className="biotwin-change"><ArrowDownRight size={17}/><strong>{values.change !== null ? `${values.change.toFixed(3)}°C` : '—'}</strong><small>Mean change</small></div>
        <div><small>After</small><strong>{values.after.toFixed(2)}°C</strong></div>
      </div> : <p className="biotwin-no-metric">A complete before/after comparison was not returned by this source.</p>}
      {values.p !== null && <div className="biotwin-stat-line"><span>Adjusted p-value</span><strong>{values.p.toFixed(4)}</strong></div>}
    </article>
  )
  return (
    <div className="biotwin-dashboard">
      {result?.answer && <section className="biotwin-generated-answer">
        <div className="biotwin-generated-answer-head">
          <div><span className="biotwin-kicker">BIOTWIN AI SYNTHESIS</span><h4>{result.generation_status === 'success' ? 'Evidence-grounded research answer' : 'Evidence retrieval response'}</h4></div>
          <span className={`biotwin-generation-state ${result.generation_status === 'success' ? 'is-live' : 'is-fallback'}`}>
            {result.generation_status === 'success' ? `Groq · ${result.model || 'LLM'}` : 'Retrieval fallback'}
          </span>
        </div>
        <ResearchMarkdown content={result.answer}/>
        {result.citations?.length > 0 && <div className="biotwin-answer-citations"><b>Retrieved sources</b><div>{result.citations.map((source, index) => <span key={source.evidence_id || index}>{source.title}</span>)}</div></div>}
      </section>}
      <div className="biotwin-result-banner">
        <div><span className="biotwin-kicker">RESEARCH BRIEF</span><h3>{core || mean ? 'Physiological response to heat acclimation' : 'Research evidence overview'}</h3><p>{participantsMatch?.[1] ? `Human acclimation study · ${participantsMatch[1]} participants · Group-level findings` : 'Findings retrieved from the currently indexed research sources'} · Not individual worker predictions.</p></div>
        <span className="biotwin-status"><span/> {result?.generation_status === "success" ? "AI synthesis generated" : "Evidence retrieved"}</span>
      </div>

      <div className="biotwin-section-title"><div><span className="biotwin-kicker">KEY FINDINGS</span><h4>Temperature measurements</h4></div><span>Paired pre / post analysis</span></div>
      <div className="biotwin-findings-grid">
        {core && <Finding title="Core body temperature" values={coreValues}/>}
        {mean && <Finding title="Mean body temperature" values={meanValues}/>}
        {!core && !mean && <div className="biotwin-empty">No temperature comparison was returned for this question. Review the indexed sources below.</div>}
      </div>
      <div className="biotwin-interpretation"><Info size={17}/><div><strong>Scientific interpretation</strong><p>These are group-level changes from a small study. They do not establish causation, diagnose heat illness, or validate a worker-level risk model.</p></div></div>
      {prospie && <details className="biotwin-validation-details">
        <summary><span><b>PROSPIE model validation</b><small>Open methodology and cross-validation design</small></span><ChevronDown size={16}/></summary>
        <div className="biotwin-validation-grid">
          <div><span>Participant-condition samples</span><strong>{sampleMatch?.[1] || '—'}</strong></div>
          <div><span>Unique participants</span><strong>{uniqueMatch?.[1] || '—'}</strong></div>
          <div><span>Outer folds</span><strong>{outerMatch?.[1] || '—'}</strong></div>
          <div><span>Inner folds</span><strong>{innerMatch?.[1] || '—'}</strong></div>
        </div>
        <p>Nested GroupKFold validation keeps participant groups separate between training and held-out folds. The target was mean work-phase rectal core temperature. Fold counts describe the experiment design, not model accuracy.</p>
        <div className="biotwin-model-results">
          <div className="biotwin-model-results-heading">
            <div><b>Model performance comparison</b><small>Nested participant-held-out validation · Temperature error in °C</small></div>
            <span>Exploratory</span>
          </div>
          <div className="biotwin-model-table-wrap">
            <table className="biotwin-model-table">
              <thead><tr><th>Model</th><th>MAE ↓</th><th>RMSE ↓</th><th>R² ↑</th></tr></thead>
              <tbody>
                <tr className="biotwin-model-highlight"><td>Ridge regression</td><td>0.1842</td><td>0.2434</td><td>−0.0265</td></tr>
                <tr><td>Condition-aware baseline</td><td>0.1887</td><td>0.2398</td><td>0.0036</td></tr>
                <tr><td>Dummy baseline</td><td>0.1931</td><td>0.2435</td><td>−0.0273</td></tr>
                <tr><td>XGBoost</td><td>0.2013</td><td>0.2519</td><td>−0.0991</td></tr>
                <tr><td>Random Forest</td><td>0.2053</td><td>0.2609</td><td>−0.1791</td></tr>
              </tbody>
            </table>
          </div>
          <div className="biotwin-model-takeaway">
            <b>What the results indicate</b>
            <p>Ridge achieved the lowest MAE, while the condition-aware baseline had the best RMSE and R². Overall performance does not establish reliable predictive capability beyond the baselines.</p>
          </div>
        </div>
      </details>}
      <div className="biotwin-section-title biotwin-method-title"><div><span className="biotwin-kicker">TRACEABILITY</span><h4>Research sources</h4></div><span>{Math.min(evidence.length, 3)} key sources</span></div>
      <div className="research-source-list">{evidence.slice(0, 3).map((item, index) => <ResearchEvidenceCard key={`${item.source}-${index}`} item={item}/>)}</div>
    </div>
  )
}

function StatusPill({ level, children }) {

  return <span className={`status-pill ${level}`}>{children || (level === 'high' ? 'High risk' : level === 'watch' ? 'Watch' : 'Lower risk')}</span>

}

function Brand() {

  return <div className="brand-mark"><div className="brand-shield"><ShieldCheck size={21}/></div><div><b>heatshield<span>ai</span></b><small>WORKER PROTECTION</small></div></div>

}

function MainApp({ currentUser, onLogout, initialView }) {

  const roleHome = {
    admin: 'overview',
    executive: 'overview',
    supervisor: 'overview',
    health_safety: 'auraheat',
    researcher: 'biotwin',
    worker: 'worker',
  }
  
  const [view, setView] = useState(
    initialView || roleHome[currentUser.role] || 'overview'
  )

  const [mobileMenu, setMobileMenu] = useState(false)

  const [showAssessment, setShowAssessment] = useState(false)

  const [assessment, setAssessment] = useState({ wbgt: '', workload: 'Heavy', acclimatized: false, exposureHours: '2', clothingAdjustment: 0 })

  const [result, setResult] = useState(null)

  const [notification, setNotification] = useState('')

  const [installPrompt, setInstallPrompt] = useState(null)

  const [showSources, setShowSources] = useState(false)

  const [weatherCity, setWeatherCity] = useState('abu_dhabi')

  const [weatherData, setWeatherData] = useState(null)

  const [weatherLoading, setWeatherLoading] = useState(false)

  const [weatherError, setWeatherError] = useState('')

  const [dashboardData, setDashboardData] = useState({ worksites: [], workers: [], zones: [], exposures: [], interventions: [], summary: null })

  const [dashboardLoading, setDashboardLoading] = useState(false)

  const [dashboardError, setDashboardError] = useState('')

  const [researchQuestion, setResearchQuestion] = useState(
    'What changed in core temperature after heat acclimation?'
  )
  const [researchResult, setResearchResult] = useState(null)
  const [researchLoading, setResearchLoading] = useState(false)
  const [researchError, setResearchError] = useState('')




  React.useEffect(() => {

    const handler = (e) => { e.preventDefault(); setInstallPrompt(e) }

    window.addEventListener('beforeinstallprompt', handler)

    return () => window.removeEventListener('beforeinstallprompt', handler)

  }, [])






  React.useEffect(() => {

    let cancelled = false

    async function loadDashboard() {

      setDashboardLoading(true)

      setDashboardError('')

      try {

        const results = await Promise.allSettled([

          fetchWorksites(),

          fetchWorkers(),

          fetchZones(),

          fetchExposureRecords(undefined, 100),

          fetchInterventions(),

          fetchDashboardSummary(),

        ])

        if (cancelled) return

        const value = (index) => results[index].status === 'fulfilled' ? results[index].value : null

        const rows = (payload, keys) => {

          if (Array.isArray(payload)) return payload

          for (const key of keys) if (Array.isArray(payload?.[key])) return payload[key]

          return []

        }

        const worksites = rows(value(0), ['worksites', 'items', 'results', 'data'])

        const workers = rows(value(1), ['workers', 'items', 'results', 'data'])

        const zones = rows(value(2), ['zones', 'items', 'results', 'data'])

        const exposures = rows(value(3), ['exposure_records', 'records', 'items', 'results', 'data'])

        const interventions = rows(value(4), ['interventions', 'items', 'results', 'data'])

        const summary = value(5)

        const failed = results.filter(item => item.status === 'rejected')

        if (failed.length === results.length) {

          throw failed[0].reason || new Error('Could not load dashboard data.')

        }

        setDashboardData({ worksites, workers, zones, exposures, interventions, summary })

        if (failed.length) setDashboardError('Some dashboard datasets could not be loaded. Available data is shown.')

      } catch (error) {

        if (!cancelled) setDashboardError(error.message || 'Could not load dashboard data.')

      } finally {

        if (!cancelled) setDashboardLoading(false)

      }

    }

    loadDashboard()

    return () => { cancelled = true }

  }, [])



  const latestMeasuredExposure = dashboardData.exposures

    .filter(item => item.measured_wbgt_c !== null && item.measured_wbgt_c !== undefined && item.source === 'onsite_sensor')

    .sort((a, b) => new Date(b.recorded_at || 0) - new Date(a.recorded_at || 0))[0]

  const activeWorkers = dashboardData.workers.filter(worker => worker.active !== false).length

  const exposureRiskCounts = ['low', 'watch', 'high', 'critical'].map(level => ({
    level,
    count: dashboardData.exposures.filter(item => String(item.risk_level || '').toLowerCase() === level).length,
  }))
  const exposureSourceCounts = [
    { label: 'On-site sensor', count: dashboardData.exposures.filter(item => item.source === 'onsite_sensor').length },
    { label: 'Weather estimate', count: dashboardData.exposures.filter(item => item.source === 'weather_estimate').length },
    { label: 'Demo simulation', count: dashboardData.exposures.filter(item => item.source === 'demo_simulation').length },
    { label: 'Other / unspecified', count: dashboardData.exposures.filter(item => !['onsite_sensor', 'weather_estimate', 'demo_simulation'].includes(item.source)).length },
  ]
  const maxRiskCount = Math.max(1, ...exposureRiskCounts.map(item => item.count))
  const maxSourceCount = Math.max(1, ...exposureSourceCounts.map(item => item.count))
  const recentExposureRows = [...dashboardData.exposures]
    .sort((a, b) => new Date(b.recorded_at || 0) - new Date(a.recorded_at || 0)).slice(0, 6)


  React.useEffect(() => {

    let cancelled = false

    setWeatherLoading(true)

    setWeatherError('')

    fetchWeather(weatherCity)

      .then(data => { if (!cancelled) setWeatherData(data) })

      .catch(error => { if (!cancelled) setWeatherError(error.message) })

      .finally(() => { if (!cancelled) setWeatherLoading(false) })

    return () => { cancelled = true }

  }, [weatherCity])



  const notify = async () => {

    if (!('Notification' in window)) { setNotification('Notifications are not supported in this browser.'); return }

    const permission = await Notification.requestPermission()

    if (permission === 'granted') {

      new Notification('HeatShield AI notification test', { body: 'This is a local notification test only. It does not indicate a real worker exposure event.' })

      setNotification('Local notification test sent. No exposure event was generated.')

    } else setNotification('Notification permission was not granted.')

  }

  const install = async () => {

    if (!installPrompt) { setNotification('Use your browser menu and choose “Install app” or “Add to Home Screen”.'); return }

    installPrompt.prompt()

    await installPrompt.userChoice

    setInstallPrompt(null)

  }

  const runAssessment = (e) => {

    e.preventDefault()

    setResult(assessRisk({ ...assessment, wbgt: Number(assessment.wbgt), exposureHours: Number(assessment.exposureHours) }))

  }

  const handleResearchAsk = async (e) => {

    e.preventDefault()



    if (researchQuestion.trim().length < 5) {

      setResearchError('Please enter a longer research question.')

      return

    }



    setResearchLoading(true)

    setResearchError('')

    setResearchResult(null)



    try {

      const data = await askBioTwinResearch(researchQuestion.trim(), 5)

      setResearchResult(data)

    } catch (error) {

      setResearchError(error.message || 'Could not retrieve research evidence.')

    } finally {

      setResearchLoading(false)

    }

  }

  const allNav = [
    { id: 'overview', label: 'Command Center', icon: ChartNoAxesCombined,
      roles: ['admin', 'executive', 'supervisor'] },
  
    { id: 'worker', label: 'Worker Portal', icon: Home,
      roles: ['admin', 'worker'] },
  
    { id: 'auraheat', label: 'AuraHeat Monitoring', icon: Activity,
      roles: ['admin', 'supervisor', 'health_safety'] },
  
    { id: 'equiclimate', label: 'EquiClimate', icon: Thermometer,
      roles: ['admin', 'supervisor', 'health_safety'] },
  
    { id: 'biotwin', label: 'BioTwin Research', icon: HeartPulse,
      roles: ['admin', 'researcher'] },
  
    { id: 'mesh', label: 'BioShield Mesh', icon: Wifi,
      roles: ['admin', 'supervisor'] },
  
    { id: 'preventive', label: 'Preventive Care', icon: ShieldCheck,
      roles: ['admin', 'supervisor', 'health_safety'] },
  
    { id: 'analytics', label: 'Analytics & Reports', icon: ChartNoAxesCombined,
      roles: ['admin', 'executive', 'supervisor'] },
    
    {
      id: 'admin-users',
      label: 'User Management',
      icon: Users,
      roles: ['admin']
    },
    { id: 'workforce', label: 'Workforce Management', icon: Users,
      roles: ['admin', 'supervisor'] },

    {
      id: 'worksites',
      label: 'Worksite Management',
      icon: Building2,
      roles: ['admin', 'supervisor']
    },

  ]
  
  const nav = allNav.filter(item =>
    item.roles.includes(currentUser.role)
  )

  return <div className="app-shell">

    <aside className={`sidebar ${mobileMenu ? 'open' : ''}`}>

      <div className="sidebar-top"><Brand/><button className="icon-btn mobile-close" onClick={() => setMobileMenu(false)}><X/></button></div>

      <div className="workspace-label">WORKSPACE</div>

      <nav>{nav.map(item => <button key={item.id} className={`nav-item ${view === item.id ? 'active' : ''}`} onClick={() => { setView(item.id); setMobileMenu(false) }}><item.icon size={18}/>{item.label}{view === item.id && <span className="nav-dot"/>}</button>)}</nav>

      <div className="sidebar-spacer"/>

      <div className="sidebar-help"><div className="help-icon"><CircleHelp size={18}/></div><b>Need help?</b><p>Learn how to stay safe in hot conditions.</p><button onClick={() => setShowSources(true)}>Safety guidance <ArrowUpRight size={14}/></button></div>

      <div className="profile-row">
        <div className="avatar">
          {currentUser.full_name?.charAt(0)?.toUpperCase() || 'H'}
        </div>
        <div>
          <b>{currentUser.full_name}</b>
          <small>{currentUser.role.replaceAll('_', ' ').toUpperCase()}</small>
        </div>
        <ChevronDown size={16}/>
      </div>

    </aside>



    <main className="main">

      <header className="topbar">

        <button className="icon-btn menu-toggle" onClick={() => setMobileMenu(true)}><Menu/></button>

        <div className="breadcrumb">Workspace <span>/</span> <b>{nav.find(item => item.id === view)?.label || 'Overview'}</b></div>

        <div className="top-actions"><span className="demo-tag"><span/> AUTHENTICATED WORKSPACE</span><button className="icon-btn" onClick={notify} aria-label="Enable notifications"><Bell size={18}/></button><div className="hs-session-pill"><span className="hs-session-dot"/><span>{currentUser.full_name}</span><small>{String(currentUser.role).replaceAll('_', ' ')}</small><button onClick={onLogout}>Sign out</button></div></div>

      </header>

    
      {view === 'admin-users' && currentUser.role === 'admin'
      ? <AdminUsers />
      : view === 'workforce' ? <WorkforcePortal />
      : view === 'worksites' ? <WorksitePortal />
      : view === 'auraheat' ? <AuraHeatPortal />
      : view === 'equiclimate' ? <EquiClimatePortal />
      : view === 'worker' ? <section className="content">
        <div className="welcome-row"><div><div className="eyebrow">WORKER SAFETY WORKSPACE</div><h1>Worker safety briefing</h1><p className="muted">Live personal exposure information appears only when a verified worker profile and current source data are connected.</p></div><button className="btn btn-dark install-btn" onClick={install}><Smartphone size={16}/>{installPrompt ? 'Install app' : 'Add to home screen'}</button></div>
        <div className="card" style={{padding:'28px',marginTop:'22px'}}><div className="eyebrow">NO VERIFIED WORKER SESSION</div><h2>Personal exposure status unavailable</h2><p className="muted">No authenticated worker profile or live personal sensor feed is connected in this workspace. HeatShield will not display an illustrative WBGT value, infer that conditions are safe, or generate an individual health probability.</p><div className="notice"><Info size={17}/><p>Use the supervisor workspace to review registered worksites, recorded exposure entries, evidence and preventive actions. Weather forecasts are contextual information and are not on-site WBGT measurements.</p></div></div>
      </section> : view !== 'overview' ? <ModuleWorkspace view={view} data={dashboardData} onRefresh={() => {}} /> : <section className="content">

        {dashboardError && <div className="notice"><Info size={17}/><p>{dashboardError}</p></div>}
        {dashboardLoading && <div className="card weather-state">Loading worksite data from HeatShield API…</div>}

        <section className="command-center">
          <header className="command-center-brand">
            <div className="command-center-brand-left">
              <span className="command-center-shield"><ShieldCheck size={23}/></span>
              <b>HEATSHIELD AI</b>
            </div>
            <span className="command-center-live"><i/> RECORDED DATA VIEW</span>
          </header>

          <div className="command-center-heading">
            <h2>Executive Command Center</h2>
            <span>Abu Dhabi Pilot</span>
          </div>

          <div className="command-center-metrics">
            <article className="command-center-metric">
              <span>REGISTERED ACTIVE WORKERS</span>
              <strong>{String(activeWorkers).padStart(2, '0')}</strong>
            </article>
            <article className="command-center-metric">
              <span>WORKSITES</span>
              <strong>{String(dashboardData.worksites.length).padStart(2, '0')}</strong>
            </article>
            <article className="command-center-metric is-alert">
              <span>HIGH / CRITICAL RECORDS</span>
              <strong>{String(dashboardData.exposures.filter(item => ['high', 'critical'].includes(String(item.risk_level || '').toLowerCase())).length).padStart(2, '0')}</strong>
            </article>
            <article className="command-center-metric">
              <span>INTERVENTIONS</span>
              <strong>{String(dashboardData.interventions.length).padStart(2, '0')}</strong>
            </article>
          </div>

          <section className="command-center-safety">
            <h3>Workforce Safety Overview</h3>
            <div className="command-center-data-row">
              <span>Simulated exposure records</span>
              <strong className="command-center-demo">{String(dashboardData.exposures.filter(item => item.source === 'demo_simulation').length).padStart(2, '0')} <i>DEMO DATA</i></strong>
            </div>
            <div className="command-center-data-row">
              <span>On-site measured WBGT</span>
              <strong className={latestMeasuredExposure ? 'command-center-measured' : 'command-center-unavailable'}>
                {latestMeasuredExposure ? `${Number(latestMeasuredExposure.measured_wbgt_c).toFixed(1)}°C` : 'Not available'}
              </strong>
            </div>
          </section>

          <footer className="command-center-legend">
            <span><i className="legend-teal"/> Teal — primary interface</span>
            <span><i className="legend-orange"/> Orange — alerts</span>
          </footer>
        </section>

        <div className="command-center-toolbar">
          <div><div className="eyebrow">OPERATIONS OVERVIEW</div><p className="muted">A snapshot of saved workforce and worksite records. Live sensor feeds are not connected.</p></div>
          <button className="btn btn-dark" onClick={notify}><Bell size={16}/> Test alert</button>
        </div>

        <section className="command-analytics-grid">
          <article className="card analytics-panel">
            <div className="analytics-panel-head"><div><div className="eyebrow">EXPOSURE DISTRIBUTION</div><h3>Recorded risk levels</h3></div><span className="analytics-total">{dashboardData.exposures.length} records</span></div>
            {dashboardData.exposures.length ? <div className="analytics-bars">{exposureRiskCounts.map(item => <div className="analytics-bar-row" key={item.level}><span>{item.level.toUpperCase()}</span><div className="analytics-track"><i className={`risk-bar ${item.level}`} style={{width:`${item.count / maxRiskCount * 100}%`}}/></div><b>{item.count}</b></div>)}</div> : <div className="analytics-empty">No exposure records available to chart yet.</div>}
            <p className="analytics-footnote">Counts reflect saved exposure records only; they are not live sensor readings.</p>
          </article>
          <article className="card analytics-panel">
            <div className="analytics-panel-head"><div><div className="eyebrow">DATA PROVENANCE</div><h3>Exposure record sources</h3></div><span className="analytics-total">{dashboardData.exposures.length} records</span></div>
            {dashboardData.exposures.length ? <div className="analytics-bars">{exposureSourceCounts.map(item => <div className="analytics-bar-row" key={item.label}><span>{item.label}</span><div className="analytics-track"><i className="source-bar" style={{width:`${item.count / maxSourceCount * 100}%`}}/></div><b>{item.count}</b></div>)}</div> : <div className="analytics-empty">Source breakdown will appear when exposure records are saved.</div>}
            <p className="analytics-footnote">Demo and weather-estimated records remain distinct from on-site sensor measurements.</p>
          </article>
        </section>

        <div className="section-heading"><div><div className="eyebrow">WORKSITE MONITORING</div><h2>Registered worksites</h2></div><span className="demo-tag"><span/> DATABASE RECORDS</span></div>

        <div className="card site-table">

          <div className="table-head"><span>WORKSITE</span><span>LOCATION / TYPE</span><span>ZONES</span><span>WORKERS</span><span>EXPOSURE RECORDS</span><span>STATUS</span></div>

          {dashboardData.worksites.length === 0 && !dashboardLoading && <div className="weather-state">No worksites registered yet. Add a worksite through the API to see it here.</div>}

          {dashboardData.worksites.map(site => {

            const siteId = site.id ?? site.worksite_id

            const siteWorkers = dashboardData.workers.filter(worker => String(worker.worksite_id) === String(siteId))

            const siteZones = dashboardData.zones.filter(zone => String(zone.worksite_id) === String(siteId))

            const siteExposures = dashboardData.exposures.filter(record => String(record.worksite_id) === String(siteId))

            const hasHigh = siteExposures.some(record => ['high', 'critical'].includes(String(record.risk_level || '').toLowerCase()))
            const hasDemoRecords = siteExposures.some(record => record.source === 'demo_simulation')
            const hasOnsiteEntries = siteExposures.some(record => record.source === 'onsite_sensor' && record.measured_wbgt_c !== null && record.measured_wbgt_c !== undefined)

            const siteStatus = hasOnsiteEntries
              ? (hasHigh ? 'High-risk entries' : 'On-site entries')
              : hasDemoRecords
                ? 'Demo records'
                : siteExposures.length
                  ? 'Recorded entries'
                  : 'No records'

            return <div className="table-row" key={siteId}><div className="site-name"><div className="site-icon"><Building2 size={17}/></div><b>{site.name || site.site_name || `Worksite ${siteId}`}</b></div><span>{site.location || site.industry || site.type || '—'}</span><span>{siteZones.length}</span><span>{siteWorkers.length}</span><span>{siteExposures.length}</span><StatusPill level={hasOnsiteEntries && hasHigh ? 'high' : 'lower'}>{siteStatus}</StatusPill></div>

          })}

        </div>

        <div className="section-heading"><div><div className="eyebrow">EXPOSURE REGISTER</div><h2>Recent exposure records</h2></div><span className="analytics-total">Latest {recentExposureRows.length} of {dashboardData.exposures.length}</span></div>
        <div className="card analytics-table-wrap"><table className="analytics-table"><thead><tr><th>RECORDED</th><th>WORKER</th><th>RISK LEVEL</th><th>WBGT</th><th>DATA SOURCE</th></tr></thead><tbody>
          {recentExposureRows.map((record, index) => <tr key={record.id ?? `${record.worker_id}-${record.recorded_at}-${index}`}><td>{record.recorded_at ? new Date(record.recorded_at).toLocaleString() : 'Time unavailable'}</td><td>{record.worker_name || record.worker_id || 'Not specified'}</td><td><span className={`analytics-risk-pill ${String(record.risk_level || 'unknown').toLowerCase()}`}>{String(record.risk_level || 'Unclassified').replaceAll('_',' ')}</span></td><td>{record.source === 'onsite_sensor' && record.measured_wbgt_c !== null && record.measured_wbgt_c !== undefined ? `${Number(record.measured_wbgt_c).toFixed(1)}°C` : 'Not measured'}</td><td>{String(record.source || 'Unspecified').replaceAll('_',' ')}</td></tr>)}
          {!recentExposureRows.length && <tr><td colSpan="5" className="analytics-empty-cell">No exposure records have been saved yet.</td></tr>}
        </tbody></table></div>

        <div className="section-heading"><div><div className="eyebrow">RECENT SAFETY ACTIVITY</div><h2>Intervention log</h2></div></div>

        <div className="supervisor-actions">

          {dashboardData.interventions.length === 0 && <div className="weather-state">No interventions have been recorded yet.</div>}

          {dashboardData.interventions.slice(0, 5).map(item => <div className="supervisor-action" key={item.id}><div className={`priority-dot ${String(item.status).toLowerCase() === 'completed' ? 'watch-dot' : 'high-dot'}`}/><div><b>{String(item.intervention_type || 'Safety intervention').replaceAll('_', ' ')}</b><p>{item.reason || 'No additional details provided.'}</p><small>{String(item.status || 'open').toUpperCase()} · {item.affected_crew_count ?? 0} WORKERS AFFECTED</small></div></div>)}

        </div>

        <div className="notice"><Info size={17}/><p>Dashboard counts and worksite records are loaded from the HeatShield backend. WBGT is displayed only when an exposure record explicitly contains an on-site sensor measurement. Weather estimates are not treated as measured WBGT.</p></div>

      </section>}

      <footer className="footer"><Brand/><span>© 2026 HeatShield AI · Integrated prototype v0.5</span><button onClick={() => setShowSources(true)}>Safety references</button></footer>

    </main>

    {notification && <div className="toast"><Check size={17}/>{notification}<button onClick={()=>setNotification('')}><X size={15}/></button></div>}

    {showSources && <div className="modal-backdrop" onClick={()=>setShowSources(false)}><div className="modal" onClick={e=>e.stopPropagation()}><button className="modal-close" onClick={()=>setShowSources(false)}><X/></button><div className="eyebrow">SAFETY & EVIDENCE</div><h2>Guidance behind HeatShield</h2><p>This prototype uses a simplified reference-threshold approach for demonstration. Thresholds must be reviewed against current local requirements and a qualified occupational-safety assessment before operational use.</p><ul><li><a href="https://www.osha.gov/heat-exposure/hazards" target="_blank" rel="noreferrer">OSHA — Heat hazard recognition</a></li><li><a href="https://www.osha.gov/heat-exposure/water-rest-shade" target="_blank" rel="noreferrer">OSHA — Water, rest and shade</a></li><li><a href="https://www.cdc.gov/niosh/heat-stress/recommendations/index.html" target="_blank" rel="noreferrer">NIOSH — Workplace recommendations</a></li><li><a href="https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps" target="_blank" rel="noreferrer">MDN — Progressive Web Apps</a></li></ul><div className="modal-note">Never use this prototype to diagnose heat illness or replace emergency response. If a worker shows signs of heat stroke, activate emergency procedures immediately.</div></div></div>}

  </div>

}


function LoginScreen({ onLogin, workspace }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError('')
    try { await onLogin(email, password) } catch (err) { setError(err.message || 'Unable to sign in.') } finally { setBusy(false) }
  }
  return <div className="hs-auth-shell"><div className="hs-auth-art"><div className="hs-auth-brand"><div className="brand-shield"><ShieldCheck size={24}/></div><div><b>heatshield<span>ai</span></b><small>WORKER PROTECTION PLATFORM</small></div></div><div className="hs-auth-copy"><span>OCCUPATIONAL HEALTH INTELLIGENCE</span><h1>Protect people.<br/>Anticipate heat risk.</h1><p>A connected command environment for workforce safety, environmental intelligence and evidence-led prevention.</p><div className="hs-auth-orbit"><div>LIVE<br/>MONITORING</div><div>HUMAN<br/>CENTRED</div><div>SAFETY<br/>FIRST</div></div></div><small className="hs-auth-foot">HEATSHIELD AI · SECURE WORKSPACE</small></div><div className="hs-auth-panel"><form className="hs-login-card" onSubmit={submit}><span className="hs-login-kicker">SECURE ACCESS</span><h2>{workspace ? `Access ${workspace.label}` : 'Welcome back'}</h2><p>{workspace ? `Sign in to continue to the ${workspace.label} workspace.` : 'Sign in to continue to your authorised workspace.'}</p><label>Work email</label><input type="email" value={email} onChange={e=>setEmail(e.target.value)} autoComplete="username" required/><label>Password</label><input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" required/><button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in securely'} <span>→</span></button>{error && <div className="hs-login-error">{error}</div>}<div className="hs-login-security"> <ShieldCheck size={16}/> Role-based access · Encrypted password storage · Expiring sessions</div></form></div></div>
}

export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const loginWorkspaceId = requestedLoginWorkspace()
  const loginWorkspace = loginWorkspaceId ? LOGIN_WORKSPACES[loginWorkspaceId] : null
  React.useEffect(() => {
    const token = localStorage.getItem('heatshield_access_token')
    if (!token) { setChecking(false); return }
    fetchCurrentUser().then((current) => {
      if (loginWorkspace && !loginWorkspace.roles.includes(current.role)) {
        localStorage.removeItem('heatshield_access_token')
        setUser(null)
        return
      }
      setUser(current)
    }).catch(() => { localStorage.removeItem('heatshield_access_token'); setUser(null) }).finally(() => setChecking(false))
  }, [])
  const handleLogin = async (email, password) => {
    const result = await loginUser(email, password)
    if (loginWorkspace && !loginWorkspace.roles.includes(result.user.role)) {
      throw new Error(`Your account does not have access to ${loginWorkspace.label}.`)
    }
    localStorage.setItem('heatshield_access_token', result.access_token)
    setUser(result.user)
  }
  const handleLogout = () => { localStorage.removeItem('heatshield_access_token'); setUser(null) }
  if (checking) return <div className="hs-auth-loading">HEATSHIELD AI <span>SECURE WORKSPACE</span></div>
  return user ? <MainApp currentUser={user} onLogout={handleLogout} initialView={loginWorkspaceId}/> : <LoginScreen onLogin={handleLogin} workspace={loginWorkspace}/>
}
