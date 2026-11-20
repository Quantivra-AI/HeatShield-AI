import React, { useEffect, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowRight, BookOpen, CheckCircle2, Clock3,
  CloudSun, Database, FileText, HeartPulse, Info, RefreshCw, MapPin,
  ShieldCheck, Thermometer, Users, Wifi, WifiOff, Zap
} from 'lucide-react'
import {
  askChronicHealth, fetchChronicHealthCatalog, fetchKnowledgeBaseStatus,
  fetchMeshStatus, fetchOfflineAlerts, fetchRiskAssessment, fetchShiftRotation,
  updateInterventionStatus, syncOfflineAlerts, createOfflineAlert, fetchInterventions, createIntervention,
  createWorker, createExposureRecord, createWorksite, createZone, fetchWorkerHealthDemo, fetchWorkerVitals, createWorkerVitals, fetchVitalsModelStatus
} from './api'

const conditions = [
  ['cardiovascular', 'Cardiovascular health'],
  ['renal', 'Kidney & renal health'],
  ['respiratory', 'Respiratory health'],
  ['metabolic', 'Metabolic health'],
  ['neurological', 'Neurological health'],
  ['pregnancy', 'Pregnancy-related considerations'],
  ['medication_interactions', 'Medication interactions'],
  ['multi_condition', 'Multiple conditions'],
]

function Metric({label,value,sub,icon:Icon}) {
  return <article className="premium-metric"><div className="premium-metric-top"><span>{label}</span>{Icon && <Icon size={17}/>}</div><strong>{value}</strong>{sub && <small>{sub}</small>}</article>
}
function EmptyState({title,body}) {
  return <div className="premium-empty"><Database size={23}/><b>{title}</b><p>{body}</p></div>
}
function cleanResearchText(value) {
  const text = String(value || '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(?:p|div|li|h[1-6]|tr)\s*>/gi, '\n')
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/\[[Ee]\d+(?:\s*,\s*[Ee]\d+)*\]/g, '')
    .replace(/\[(?:\s*E\d+\s*(?:,\s*E\d+\s*)*)\]/gi, '')
    .replace(/【(?:\s*E\d+\s*(?:,\s*E\d+\s*)*)】/gi, '')
    .replace(/\[\s*\]/g, '')
    .replace(/【\s*】/g, '')
    .replace(/\s+([.,;!?])/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/^\s*#{1,6}\s*/gm, '')
    .replace(/^\s*[-*•]+\s*/gm, '')
    .replace(/\b(?:answer_generated|valid_ids|citation_validation|generation_status)\b/gi, '');

  return text
    .split(/\r?\n/)
    .filter(line => {
      const trimmed = line.trim();

      if (!trimmed) return true;

      // Remove all pipe-delimited Markdown table rows.
      if (/[|｜]/.test(trimmed)) return false;

      // Remove Markdown table separator rows.
      if (/^:?-{2,}:?$/.test(trimmed)) return false;

      return true;
    })
    .join('\n')
    .replace(/\s+([,.;!?])/g, '$1')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{2,}/g, '\n')
    .trim();
}



function conciseAnswer(value) {
  const text = cleanResearchText(value);

  if (!text) return [];

  const chunks = text
    .split(/\n+|(?<=[.!?])\s+/)
    .map(item =>
      item
        .replace(/[*_`#]/g, '')
        .replace(/^\s*[-•]\s*/, '')
        .replace(/\s+/g, ' ')
        .trim()
    )
    .filter(item =>
      item.length >= 45 &&
      !/^(key points?|key findings?|findings?|evidence summary|supporting evidence|limitations?|conclusion|summary)\s*:?\s*$/i.test(item)
    );

  // Remove only standalone disclaimer statements.
  const useful = chunks.filter(item =>
    !/^(important disclaimer|individual-level disclaimer|safety notice|disclaimer)\b/i.test(item) &&
    !/^clinical decisions\b/i.test(item) &&
    !/^the indexed research does not provide data that can determine an individual/i.test(item)
  );

  const selected = useful.length ? useful : chunks;

  return [...new Set(selected)]
    .slice(0, 3)
    .map(item =>
      item.length > 240
        ? item.slice(0, 237).trimEnd() + '...'
        : item
    );
}


function conciseText(value, maxLength = 190) {
  const cleaned = cleanResearchText(value);
  if (!cleaned) return 'Evidence coverage not described.';
  return cleaned.length > maxLength ? `${cleaned.slice(0,maxLength-1).trimEnd()}…` : cleaned;
}

function EvidenceList({items=[]}) {
  const visibleItems = Array.isArray(items) ? items.slice(0,3) : [];
  if (!visibleItems.length) return <EmptyState title="No evidence returned" body="The current indexed library did not return evidence for this request."/>
  return <div className="evidence-list">{visibleItems.map((item,i)=><article className="evidence-item" key={item.evidence_id || i}>
    <div className="evidence-item-top"><span className="evidence-id">Source {i+1}</span><span>{item.organization || item.source || 'Indexed source'}</span></div>
    <b>{item.title || item.source}</b>
    <p>{conciseAnswer(item.content)[0]}</p>
    {String(item.content || '').length > 190 && <details className="evidence-full"><summary>View source detail</summary><p>{cleanResearchText(item.content)}</p></details>}
    <div className="evidence-meta">{item.document_type || 'Evidence source'}{item.page_start ? ` · Page ${item.page_start}${item.page_end && item.page_end !== item.page_start ? `–${item.page_end}` : ''}` : ''}</div>
    {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">Open source <ArrowRight size={13}/></a>}
  </article>)}</div>
}

export default function ModuleWorkspace({view, data, onRefresh}) {
  const [catalog,setCatalog] = useState(null)
  const [workerHealth,setWorkerHealth] = useState(null)
  const [workerVitals,setWorkerVitals] = useState([])
  const [vitalModelStatus,setVitalModelStatus] = useState(null)
  const [vitalsDraft,setVitalsDraft] = useState({
    worker_code:'',
    body_temperature_c:'',
    temperature_type:'skin',
    heart_rate_bpm:'',
    respiratory_rate_bpm:'',
    spo2_pct:'',
    systolic_bp_mmhg:'',
    diastolic_bp_mmhg:'',
    weight_kg:'',
    height_m:'',
    symptoms:'',
    source:'manual_demo'
  })
  const [workerSearch,setWorkerSearch] = useState('')
  const [healthFilter,setHealthFilter] = useState('all')
  const [kb,setKb] = useState(null)
  const [mesh,setMesh] = useState(null)
  const [offline,setOffline] = useState(null)
  const [riskAssessment,setRiskAssessment] = useState(null)
  const [rotation,setRotation] = useState(null)
  const [actionBusy,setActionBusy] = useState(false)
  const [actionMessage,setActionMessage] = useState('')
  const [alertDraft,setAlertDraft] = useState({worker_code:'',alert_type:'heat_exposure',severity:'high',message:''})
  const [liveInterventions,setLiveInterventions] = useState(null)
  const [interventionDraft,setInterventionDraft] = useState({intervention_type:'rest_break',reason:'',affected_crew_count:0,zone_id:''})
  const [loading,setLoading] = useState(false)
  const [error,setError] = useState('')
  const [condition,setCondition] = useState('renal')
  const [scope,setScope] = useState('both')
  const [question,setQuestion] = useState('')
  const [answer,setAnswer] = useState(null)
  const [asking,setAsking] = useState(false)
  const [selectedWorksiteId,setSelectedWorksiteId] = useState('')
  const [workerDraft,setWorkerDraft] = useState({worker_code:'',role:'worker',zone_id:''})
  const [exposureDraft,setExposureDraft] = useState({worker_code:'',zone_id:'',exposure_minutes:60,source:'weather_estimate',risk_level:'moderate',air_temperature_c:'',relative_humidity_pct:'',measured_wbgt_c:'',notes:''})
  const [worksiteDraft,setWorksiteDraft] = useState({name:'',city:'',industry:'construction',worker_count:0})
  const [zoneDraft,setZoneDraft] = useState({name:'',activity_type:'general',exposure_category:'moderate',worker_capacity:0})

  const firstWorksiteId = data?.worksites?.[0]?.id ?? data?.worksites?.[0]?.worksite_id
  const worksiteId = selectedWorksiteId || firstWorksiteId
  useEffect(()=>{ if (!selectedWorksiteId && firstWorksiteId) setSelectedWorksiteId(String(firstWorksiteId)) },[firstWorksiteId,selectedWorksiteId])

  const load = async () => {
    setLoading(true); setError('')
    try {
      if (view === 'biotwin') {
        const [c,k,h,v,m] = await Promise.all([fetchChronicHealthCatalog(),fetchKnowledgeBaseStatus(),fetchWorkerHealthDemo(worksiteId),fetchWorkerVitals(worksiteId),fetchVitalsModelStatus()])
        setCatalog(c); setKb(k); setWorkerHealth(h); setWorkerVitals(v?.readings || []); setVitalModelStatus(m)
      }
      if (view === 'mesh') {
        const [m,a] = await Promise.all([fetchMeshStatus(worksiteId),fetchOfflineAlerts(worksiteId)])
        setMesh(m); setOffline(a)
      }
      if (view === 'preventive' && worksiteId) { const payload=await fetchInterventions(worksiteId); setLiveInterventions(Array.isArray(payload)?payload:(payload?.interventions||[])) }
      if (view === 'auraheat' && worksiteId) {
        const [r,o] = await Promise.all([fetchRiskAssessment(worksiteId),fetchShiftRotation(worksiteId)])
        setRiskAssessment(r); setRotation(o)
      }
    } catch(e) { setError(e.message || 'Could not load module data.') }
    finally { setLoading(false) }
  }
  useEffect(()=>{load()},[view,worksiteId])

  const ask = async (e) => {
    e.preventDefault()
    setAsking(true); setAnswer(null); setError('')
    try {
      const result = await askChronicHealth({condition,scope,question:question.trim() || undefined,top_k:5})
      setAnswer({...result, answer: result?.answer ?? result?.summary ?? result?.response ?? result?.result ?? '', evidence: Array.isArray(result?.evidence) ? result.evidence : Array.isArray(result?.sources) ? result.sources : Array.isArray(result?.citations) ? result.citations : []})
    } catch(e) { setError(e.message || 'Evidence request failed.') }
    finally { setAsking(false) }
  }

  const submitVitals = async (e) => {
    e.preventDefault()
    if (!worksiteId || !vitalsDraft.worker_code.trim()) return
    setActionBusy(true); setActionMessage('')
    try {
      
  const payload = {
    worksite_id: Number(worksiteId),
    worker_code: vitalsDraft.worker_code.trim(),
    temperature_type: vitalsDraft.temperature_type,
    source: vitalsDraft.source,
    symptoms: vitalsDraft.symptoms.trim(),
    body_temperature_c: vitalsDraft.body_temperature_c === '' ? null : Number(vitalsDraft.body_temperature_c),
    heart_rate_bpm: vitalsDraft.heart_rate_bpm === '' ? null : Number(vitalsDraft.heart_rate_bpm),
    respiratory_rate_bpm: vitalsDraft.respiratory_rate_bpm === '' ? null : Number(vitalsDraft.respiratory_rate_bpm),
    spo2_pct: vitalsDraft.spo2_pct === '' ? null : Number(vitalsDraft.spo2_pct),
    systolic_bp_mmhg: vitalsDraft.systolic_bp_mmhg === '' ? null : Number(vitalsDraft.systolic_bp_mmhg),
    diastolic_bp_mmhg: vitalsDraft.diastolic_bp_mmhg === '' ? null : Number(vitalsDraft.diastolic_bp_mmhg),
    weight_kg: vitalsDraft.weight_kg === '' ? null : Number(vitalsDraft.weight_kg),
    height_m: vitalsDraft.height_m === '' ? null : Number(vitalsDraft.height_m)
  }

      const result = await createWorkerVitals(payload)
      setActionMessage(`${result.alert_level.toUpperCase()} screening flag saved for ${result.worker_code}: ${result.recommendation}.`)
      setVitalsDraft({
        ...vitalsDraft,
        body_temperature_c: '',
        heart_rate_bpm: '',
        respiratory_rate_bpm: '',
        spo2_pct: '',
        systolic_bp_mmhg: '',
        diastolic_bp_mmhg: '',
        weight_kg: '',
        height_m: '',
        symptoms: ''
      })
      const updated = await fetchWorkerVitals(worksiteId); setWorkerVitals(updated?.readings || [])
    } catch(e) { setError(e.message || 'Could not save worker reading.') }
    finally { setActionBusy(false) }
  }

  const submitWorker = async (e) => {
    e.preventDefault()
    if (!worksiteId || !workerDraft.worker_code.trim()) return
    setActionBusy(true); setActionMessage('')
    try {
      await createWorker({worksite_id:Number(worksiteId),zone_id:workerDraft.zone_id?Number(workerDraft.zone_id):null,worker_code:workerDraft.worker_code.trim(),role:workerDraft.role.trim()||'worker'})
      setWorkerDraft({worker_code:'',role:'worker',zone_id:''}); setActionMessage('Worker registered successfully.'); onRefresh?.()
    } catch(e) { setError(e.message || 'Could not register worker.') }
    finally { setActionBusy(false) }
  }

  const submitExposure = async (e) => {
    e.preventDefault()
    if (!worksiteId) return
    setActionBusy(true); setActionMessage('')
    try {
      const payload={worksite_id:Number(worksiteId),zone_id:exposureDraft.zone_id?Number(exposureDraft.zone_id):null,worker_code:exposureDraft.worker_code.trim()||null,exposure_minutes:Number(exposureDraft.exposure_minutes),source:exposureDraft.source,risk_level:exposureDraft.risk_level,air_temperature_c:exposureDraft.air_temperature_c===''?null:Number(exposureDraft.air_temperature_c),relative_humidity_pct:exposureDraft.relative_humidity_pct===''?null:Number(exposureDraft.relative_humidity_pct),measured_wbgt_c:exposureDraft.measured_wbgt_c===''?null:Number(exposureDraft.measured_wbgt_c),notes:exposureDraft.notes.trim()||null}
      await createExposureRecord(payload)
      setExposureDraft({...exposureDraft,exposure_minutes:60,air_temperature_c:'',relative_humidity_pct:'',measured_wbgt_c:'',notes:''}); setActionMessage('Exposure record saved with its source provenance.'); onRefresh?.()
    } catch(e) { setError(e.message || 'Could not save exposure record.') }
    finally { setActionBusy(false) }
  }

  const submitWorksite = async (e) => {
    e.preventDefault(); setActionBusy(true); setActionMessage('')
    try { await createWorksite({...worksiteDraft,worker_count:Number(worksiteDraft.worker_count)}); setWorksiteDraft({name:'',city:'',industry:'construction',worker_count:0}); setActionMessage('Worksite created. Select it after refreshing the workspace.'); onRefresh?.() }
    catch(e) { setError(e.message || 'Could not create worksite.') }
    finally { setActionBusy(false) }
  }

  const submitZone = async (e) => {
    e.preventDefault(); if (!worksiteId) return
    setActionBusy(true); setActionMessage('')
    try { await createZone({worksite_id:Number(worksiteId),...zoneDraft,worker_capacity:Number(zoneDraft.worker_capacity)}); setZoneDraft({name:'',activity_type:'general',exposure_category:'moderate',worker_capacity:0}); setActionMessage('Work zone created.'); onRefresh?.() }
    catch(e) { setError(e.message || 'Could not create zone.') }
    finally { setActionBusy(false) }
  }

  const addIntervention = async (e) => {
    e.preventDefault()
    if (!worksiteId || interventionDraft.reason.trim().length < 5) return
    setActionBusy(true); setActionMessage('')
    try {
      await createIntervention({worksite_id:Number(worksiteId),zone_id:interventionDraft.zone_id?Number(interventionDraft.zone_id):null,intervention_type:interventionDraft.intervention_type,reason:interventionDraft.reason.trim(),affected_crew_count:Number(interventionDraft.affected_crew_count),status:'recommended'})
      setInterventionDraft({...interventionDraft,reason:'',affected_crew_count:0})
      const payload=await fetchInterventions(worksiteId); setLiveInterventions(Array.isArray(payload)?payload:(payload?.interventions||[])); setActionMessage('Preventive action added for supervisor review.')
    } catch(e) { setError(e.message || 'Could not create intervention.') }
    finally { setActionBusy(false) }
  }

  const changeIntervention = async (id,status) => {
    setActionBusy(true); setActionMessage('')
    try { await updateInterventionStatus(id,status); setActionMessage(`Intervention ${status}.`); const payload=await fetchInterventions(worksiteId); setLiveInterventions(Array.isArray(payload)?payload:(payload?.interventions||[])); onRefresh?.() }
    catch(e) { setError(e.message || 'Could not update intervention status.') }
    finally { setActionBusy(false) }
  }
  const syncAlerts = async () => {
    if (!worksiteId) return
    setActionBusy(true); setActionMessage('')
    try { const result=await syncOfflineAlerts(worksiteId); setActionMessage(result.message || 'Sync request completed.'); await load() }
    catch(e) { setError(e.message || 'Could not synchronize queued alerts.') }
    finally { setActionBusy(false) }
  }
  const queueAlert = async (e) => {
    e.preventDefault()
    if (!worksiteId || !alertDraft.message.trim()) return
    setActionBusy(true); setActionMessage('')
    try { await createOfflineAlert({...alertDraft,worksite_id:Number(worksiteId),worker_code:alertDraft.worker_code.trim() || null}); setAlertDraft({...alertDraft,message:''}); setActionMessage('Alert queued in the backend.'); await load() }
    catch(e) { setError(e.message || 'Could not queue alert.') }
    finally { setActionBusy(false) }
  }

  const sites = data?.worksites || []
  const workers = (data?.workers || []).filter(x=>!worksiteId || String(x.worksite_id)===String(worksiteId))
  const exposures = (data?.exposures || []).filter(x=>!worksiteId || String(x.worksite_id)===String(worksiteId))
  const zones = (data?.zones || []).filter(x=>!worksiteId || String(x.worksite_id)===String(worksiteId))
  const interventions = liveInterventions ?? (data?.interventions || []).filter(x=>!worksiteId || String(x.worksite_id)===String(worksiteId))
  const measured = exposures.filter(x=>x.source==='onsite_sensor' && x.measured_wbgt_c != null)
  const stale = exposures.filter(x=>x.recorded_at && Date.now()-new Date(x.recorded_at).getTime()>24*60*60*1000)
  const latest = [...exposures].sort((a,b)=>new Date(b.recorded_at||0)-new Date(a.recorded_at||0))[0]
  const siteName = (id)=>sites.find(s=>String(s.id??s.worksite_id)===String(id))?.name || `Worksite ${id ?? '—'}`

  const titleMap = {
    auraheat:'AuraHeat', equiclimate:'EquiClimate', biotwin:'BioTwin', mesh:'BioShield Mesh',
    preventive:'Preventive Care', analytics:'Analytics & Reports'
  }
  const subtitleMap = {
    auraheat:'Worker-level exposure, available signals and transparent safety context.',
    equiclimate:'Worksite conditions, zone exposure and environmental data provenance.',
    biotwin:'Biomedical research, chronic-health evidence and explainable knowledge retrieval.',
    mesh:'Offline resilience, device visibility and alert synchronization status.',
    preventive:'Supervisor-reviewed preventive actions and intervention tracking.',
    analytics:'Operational trends calculated from recorded project data only.'
  }

  return <section className="content module-content">
    <div className="module-heading">
      <div><div className="eyebrow">HEATSHIELD INTELLIGENCE PLATFORM</div><h1>{titleMap[view] || 'HeatShield'}</h1><p>{subtitleMap[view]}</p></div>
      <div className="module-heading-actions">{(data?.worksites||[]).length>0 && <label className="worksite-select-label">Active worksite<select aria-label="Active worksite" value={String(worksiteId||'')} onChange={e=>setSelectedWorksiteId(e.target.value)}>{data.worksites.map(site=><option key={site.id??site.worksite_id} value={String(site.id??site.worksite_id)}>{site.name} · {site.city}</option>)}</select></label>}<button className="btn btn-dark" onClick={()=>{load();onRefresh?.()}}><RefreshCw size={15}/> Refresh data</button></div>
    </div>
    {error && <div className="module-alert"><AlertTriangle size={17}/>{error}</div>}
    {loading && <div className="module-alert"><RefreshCw size={16}/> Loading live module data…</div>}

    {view==='auraheat' && <>
      <div className="premium-metrics">
        <Metric label="REGISTERED WORKERS" value={workers.length} sub="Actual database records" icon={Users}/>
        <Metric label="EXPOSURE RECORDS" value={exposures.length} sub="Recorded exposure entries" icon={Activity}/>
        <Metric label="LATEST MEASUREMENT" value={latest?.air_temperature_c != null ? `${latest.air_temperature_c}°C` : '—'} sub={latest?.source || 'No measurement'} icon={Thermometer}/>
        <Metric label="STALE RECORDS" value={stale.length} sub="Older than 24 hours" icon={Clock3}/>
      </div>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">WORKER MANAGEMENT</span><h2>Register a worker</h2></div><span className="data-chip">DATABASE WORKFLOW</span></div>
        <form className="chi-form" onSubmit={submitWorker}><label>Worker code<input required minLength={2} maxLength={40} value={workerDraft.worker_code} onChange={e=>setWorkerDraft({...workerDraft,worker_code:e.target.value})} placeholder="e.g. WRK-006"/></label><label>Role<input value={workerDraft.role} onChange={e=>setWorkerDraft({...workerDraft,role:e.target.value})} placeholder="Worker role"/></label><label>Zone<select value={workerDraft.zone_id} onChange={e=>setWorkerDraft({...workerDraft,zone_id:e.target.value})}><option value="">No zone assigned</option>{zones.map(z=><option key={z.id} value={z.id}>{z.name}</option>)}</select></label><button className="btn btn-dark" disabled={!worksiteId||actionBusy}>Register worker <ArrowRight size={15}/></button></form>
      </div>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">EXPOSURE DATA ENTRY</span><h2>Record a worksite exposure</h2></div><span className="data-chip">SOURCE REQUIRED</span></div>
        <form className="chi-form" onSubmit={submitExposure}><label>Worker<select value={exposureDraft.worker_code} onChange={e=>setExposureDraft({...exposureDraft,worker_code:e.target.value})}><option value="">Worksite / zone-level record</option>{workers.map(w=><option key={w.id} value={w.worker_code}>{w.worker_code}</option>)}</select></label><label>Zone<select value={exposureDraft.zone_id} onChange={e=>setExposureDraft({...exposureDraft,zone_id:e.target.value})}><option value="">No zone selected</option>{zones.map(z=><option key={z.id} value={z.id}>{z.name}</option>)}</select></label><label>Duration (minutes)<input type="number" min="0" max="1440" required value={exposureDraft.exposure_minutes} onChange={e=>setExposureDraft({...exposureDraft,exposure_minutes:e.target.value})}/></label><label>Data source<select value={exposureDraft.source} onChange={e=>setExposureDraft({...exposureDraft,source:e.target.value,measured_wbgt_c:e.target.value==='onsite_sensor'?exposureDraft.measured_wbgt_c:''})}><option value="weather_estimate">Weather estimate / contextual</option><option value="onsite_sensor">On-site sensor</option></select></label><label>Exposure band<select value={exposureDraft.risk_level} onChange={e=>setExposureDraft({...exposureDraft,risk_level:e.target.value})}><option value="low">Low</option><option value="moderate">Moderate</option><option value="high">High</option><option value="critical">Critical</option></select></label><label>Air temperature °C<input type="number" step="0.1" value={exposureDraft.air_temperature_c} onChange={e=>setExposureDraft({...exposureDraft,air_temperature_c:e.target.value})}/></label><label>Relative humidity %<input type="number" min="0" max="100" step="0.1" value={exposureDraft.relative_humidity_pct} onChange={e=>setExposureDraft({...exposureDraft,relative_humidity_pct:e.target.value})}/></label>{exposureDraft.source==='onsite_sensor' && <label>Measured WBGT °C<input type="number" step="0.1" value={exposureDraft.measured_wbgt_c} onChange={e=>setExposureDraft({...exposureDraft,measured_wbgt_c:e.target.value})}/></label>}<label>Notes<textarea rows="2" value={exposureDraft.notes} onChange={e=>setExposureDraft({...exposureDraft,notes:e.target.value})} placeholder="Optional source / context notes"/></label><button className="btn btn-dark" disabled={!worksiteId||actionBusy}>Save exposure record <ArrowRight size={15}/></button></form>
        <div className="module-alert"><Info size={16}/>Only select “On-site sensor” when the measurement genuinely comes from a calibrated on-site device. This form does not create sensor data automatically.</div>
      </div>
      {actionMessage && <div className="module-alert"><CheckCircle2 size={16}/>{actionMessage}</div>}
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">WORKER REGISTER</span><h2>Worker exposure overview</h2></div><span className="data-chip">REAL DATABASE RECORDS</span></div>
        {!workers.length ? <EmptyState title="No workers registered" body="Worker records will appear here when available through the backend."/> :
        <div className="responsive-table"><table><thead><tr><th>Worker code</th><th>Role</th><th>Worksite</th><th>Latest exposure</th><th>Data status</th></tr></thead><tbody>{workers.map(w=>{
          const rec=[...exposures].filter(x=>x.worker_code===w.worker_code).sort((a,b)=>new Date(b.recorded_at||0)-new Date(a.recorded_at||0))[0]
          return <tr key={w.id || w.worker_code}><td><b>{w.worker_code}</b></td><td>{w.role || 'Worker'}</td><td>{siteName(w.worksite_id)}</td><td>{rec ? `${rec.exposure_minutes ?? '—'} min · ${rec.air_temperature_c ?? '—'}°C` : 'No exposure record'}</td><td><span className={`status-tag ${rec?'status-watch':'status-muted'}`}>{rec ? rec.source==='demo_simulation'?'Demo record':'Record available':'Insufficient data'}</span></td></tr>
        })}</tbody></table></div>}
      </div>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">EXPOSURE SCREENING · PROTOTYPE</span><h2>Worker exposure intelligence</h2></div><span className="data-chip">NOT A MEDICAL SCORE</span></div>
        {!riskAssessment ? <EmptyState title="Assessment unavailable" body="A registered worksite and backend risk assessment are required."/> : <><p>{riskAssessment.notice}</p><div className="responsive-table"><table><thead><tr><th>Worker</th><th>Exposure band</th><th>Reasons</th><th>Data source</th><th>Recorded</th></tr></thead><tbody>{(riskAssessment.results||[]).map(r=><tr key={r.worker_code}><td><b>{r.worker_code}</b></td><td><span className={`status-tag ${r.risk_band==='critical'||r.risk_band==='high'?'status-high':r.risk_band==='unknown'?'status-muted':'status-watch'}`}>{r.risk_band==='unknown'?'Unknown':`Exposure ${r.risk_band}`}</span></td><td>{(r.reasons||[]).join(' · ') || 'No supported assessment'}</td><td>{r.source || 'No record'}</td><td>{r.recorded_at ? new Date(r.recorded_at).toLocaleString() : '—'}</td></tr>)}</tbody></table></div></>}
        <div className="module-alert"><Info size={16}/>This backend heuristic is an experimental exposure-screening aid only. It is not clinically validated, does not estimate disease probability, and must not determine fitness for work.</div>
      </div>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">SHIFT PLANNING</span><h2>Rest-zone rotation suggestions</h2></div><span className="data-chip">SUPERVISOR DECISION</span></div>
        {rotation ? <><p>{rotation.notice || rotation.message || 'Suggestions based on configured zones and available records.'}</p>{(rotation.recommendations||[]).length ? <div className="responsive-table"><table><thead><tr><th>Worker</th><th>Suggested destination</th><th>Reason</th></tr></thead><tbody>{rotation.recommendations.map((r,i)=><tr key={i}><td>{r.worker_code}</td><td>{r.destination_zone || r.zone_name || 'Rest zone'}</td><td>{r.reason || 'Prototype recommendation'}</td></tr>)}</tbody></table></div> : <EmptyState title="No rotation suggestions" body={rotation.message || 'No eligible recommendation was returned.'}/>}</> : <EmptyState title="No rotation data" body="Configure a low-exposure rest zone and provide exposure records to calculate suggestions."/>}
      </div>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">ASSESSMENT BOUNDARIES</span><h2>What the current data can support</h2></div></div><div className="insight-grid"><div><CheckCircle2/><b>Exposure visibility</b><p>Show recorded duration, temperature, source and timestamp.</p></div><div><Info/><b>Vulnerability data gaps</b><p>No individual health-risk assessment without documented worker health information and a supported methodology.</p></div><div><ShieldCheck/><b>Preventive guidance</b><p>Display evidence-backed workplace controls without diagnosing workers.</p></div></div></div>
    </>}

    {view==='equiclimate' && <>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">SITE MANAGEMENT</span><h2>Create worksite</h2></div></div><form className="chi-form" onSubmit={submitWorksite}><label>Worksite name<input required minLength={2} value={worksiteDraft.name} onChange={e=>setWorksiteDraft({...worksiteDraft,name:e.target.value})}/></label><label>City<input required minLength={2} value={worksiteDraft.city} onChange={e=>setWorksiteDraft({...worksiteDraft,city:e.target.value})}/></label><label>Industry<input required minLength={2} value={worksiteDraft.industry} onChange={e=>setWorksiteDraft({...worksiteDraft,industry:e.target.value})}/></label><label>Declared workforce<input type="number" min="0" value={worksiteDraft.worker_count} onChange={e=>setWorksiteDraft({...worksiteDraft,worker_count:e.target.value})}/></label><button className="btn btn-dark" disabled={actionBusy}>Create worksite <ArrowRight size={15}/></button></form></div>
      {worksiteId && <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">ZONE MANAGEMENT</span><h2>Add work zone to {siteName(worksiteId)}</h2></div></div><form className="chi-form" onSubmit={submitZone}><label>Zone name<input required minLength={2} value={zoneDraft.name} onChange={e=>setZoneDraft({...zoneDraft,name:e.target.value})}/></label><label>Activity type<input value={zoneDraft.activity_type} onChange={e=>setZoneDraft({...zoneDraft,activity_type:e.target.value})}/></label><label>Exposure category<select value={zoneDraft.exposure_category} onChange={e=>setZoneDraft({...zoneDraft,exposure_category:e.target.value})}><option value="low">Low</option><option value="moderate">Moderate</option><option value="high">High</option></select></label><label>Worker capacity<input type="number" min="0" value={zoneDraft.worker_capacity} onChange={e=>setZoneDraft({...zoneDraft,worker_capacity:e.target.value})}/></label><button className="btn btn-dark" disabled={actionBusy}>Add zone <ArrowRight size={15}/></button></form></div>}
      <div className="premium-metrics">
        <Metric label="WORKSITES" value={sites.length} sub="Registered sites" icon={Database}/>
        <Metric label="ZONES" value={zones.length} sub="Registered work zones" icon={Thermometer}/>
        <Metric label="MEASURED WBGT" value={measured.length} sub="On-site sensor records only" icon={Activity}/>
        <Metric label="EXPOSURE ENTRIES" value={exposures.length} sub="All recorded sources" icon={CloudSun}/>
      </div>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">ENVIRONMENTAL INTELLIGENCE</span><h2>Registered worksite zones</h2></div><span className="data-chip">MEASURED ≠ ESTIMATED</span></div>
      {!zones.length ? <EmptyState title="No zones available" body="Add worksite zones to see the environmental layout."/> :
      <div className="zone-grid">{zones.map(z=><article className="zone-card" key={z.id}><div className="zone-card-icon"><Thermometer/></div><div><b>{z.name}</b><small>{siteName(z.worksite_id)}</small></div><span className={`status-tag ${z.exposure_category==='high'?'status-high':'status-watch'}`}>{z.exposure_category || 'Unknown'}</span><p>{z.activity_type || 'Activity not specified'} · Capacity {z.worker_capacity ?? '—'}</p></article>)}</div>}</div>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">WORKSITE DIGITAL TWIN</span><h2>Zone relationship view</h2></div><span className="data-chip">SCHEMATIC · NOT GEO-MAPPED</span></div>
        {!zones.length ? <EmptyState title="No site layout available" body="Register zones to build a schematic worksite view."/> : <div className="zone-grid">{zones.map((z,i)=><article className="zone-card" key={`twin-${z.id}`}><div className="zone-card-icon"><MapPin/></div><div><b>{z.name}</b><small>{siteName(z.worksite_id)}</small></div><span className="status-tag status-muted">Zone {i+1}</span><p>Occupancy and sensor position are not spatially mapped in the current dataset.</p></article>)}</div>}
        <div className="module-footnote"><Info size={15}/>This is a zone register visualization only. No coordinates, floor plan, live sensor position or unrecorded environmental values are inferred.</div>
      </div>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">DATA PROVENANCE</span><h2>Recent exposure measurements</h2></div></div>
      {!exposures.length ? <EmptyState title="No exposure data" body="Environmental risk remains unknown until actual records are available."/> :
      <div className="responsive-table"><table><thead><tr><th>Worksite</th><th>Duration</th><th>Air temperature</th><th>WBGT</th><th>Source</th><th>Recorded</th></tr></thead><tbody>{exposures.slice(0,20).map((x,i)=><tr key={x.id||i}><td>{siteName(x.worksite_id)}</td><td>{x.exposure_minutes ?? '—'} min</td><td>{x.air_temperature_c ?? '—'}°C</td><td>{x.source==='onsite_sensor' && x.measured_wbgt_c!=null ? `${x.measured_wbgt_c}°C` : 'Not measured'}</td><td>{x.source || 'Unknown'}</td><td>{x.recorded_at ? new Date(x.recorded_at).toLocaleString() : '—'}</td></tr>)}</tbody></table></div>}</div>
    </>}

    {view==='biotwin' && <>
      <div className="premium-metrics">
        <Metric label="KNOWLEDGE BASE" value={kb?.status || catalog?.status || '—'} sub="Current backend status" icon={Database}/>
        <Metric label="INDEXED DOCUMENTS" value={kb?.document_count ?? kb?.total_documents ?? '—'} sub="As reported by API" icon={BookOpen}/>
        <Metric label="HEALTH DOMAINS" value={Object.keys(catalog?.supported_topics || {}).length || '—'} sub="Configured evidence categories" icon={HeartPulse}/>
        <Metric label="EVIDENCE SOURCES" value={catalog?.indexed_clinical_and_occupational_sources?.length ?? '—'} sub="Clinical / occupational sources" icon={FileText}/>
      </div>
      <div className="module-panel chi-panel"><div className="panel-heading"><div><span className="eyebrow">CHRONIC HEALTH INTELLIGENCE</span><h2>Explore heat-related health evidence</h2><p>Research-grounded explanations of heat aggravation, vulnerabilities and evidence gaps.</p></div><span className="data-chip">EVIDENCE-ONLY</span></div>
        <div className="chi-layout"><aside className="condition-list"><span className="eyebrow">HEALTH DOMAINS</span>{conditions.map(([id,label])=><button key={id} className={condition===id?'selected':''} onClick={()=>{setCondition(id);setAnswer(null)}}>{label}<ArrowRight size={14}/></button>)}</aside>
          <div className="chi-main"><form onSubmit={ask} className="chi-form"><label>Evidence scope<select value={scope} onChange={e=>setScope(e.target.value)}><option value="both">Heat aggravation + long-term evidence</option><option value="heat_aggravation">Heat aggravation of existing condition</option><option value="long_term_development">Long-term development / progression evidence</option></select></label><label>Research question (optional)<textarea value={question} onChange={e=>setQuestion(e.target.value)} placeholder="e.g. What does indexed evidence say about occupational heat and kidney health?" rows={3}/></label><button className="btn btn-dark" disabled={asking}>{asking?'Retrieving evidence…':'Retrieve evidence'} <ArrowRight size={15}/></button></form>
            {answer && <div className="answer-panel"><div className="answer-status"><span className="eyebrow">RESEARCH SUMMARY</span><span className="data-chip">Evidence-based</span></div><div className="answer-copy"><b>Key points</b><ul>{conciseAnswer(answer.answer).map((line,i)=><li key={i}>{line}</li>)}</ul>{String(answer.answer || '').length > 380 && <details className="answer-full"><summary>Read full research response</summary><p>{cleanResearchText(answer.answer)}</p></details>}</div>{answer.safety_notice && <div className="module-alert"><Info size={16}/>{cleanResearchText(answer.safety_notice)}</div>}<div className="evidence-heading"><b>Supporting sources</b><span>Up to 3 relevant references</span></div><EvidenceList items={answer.evidence || []}/></div>}
            {!answer && <div className="chi-intro"><HeartPulse size={24}/><b>{conditions.find(x=>x[0]===condition)?.[1]}</b><p>Select a domain and retrieve the currently indexed evidence. The system will identify supported findings and gaps; it will not invent an individual disease probability.</p></div>}
          </div>
        </div>
        {catalog?.condition_evidence_coverage?.[condition] && <div className="selected-condition-note"><b>{conditions.find(x=>x[0]===condition)?.[1]} · Evidence coverage</b><span>{String(catalog.condition_evidence_coverage[condition]?.coverage || 'not assessed').replaceAll('_',' ')}</span><p>{conciseText(catalog.condition_evidence_coverage[condition]?.gap || 'Evidence coverage not described.', 190)}</p></div>}
        {catalog?.notice && <div className="module-footnote"><Info size={15}/>{catalog.notice}</div>}
      </div>
      <div className="module-panel worker-health-panel">
        <div className="panel-heading"><div><span className="eyebrow">WORKER HEALTH INTELLIGENCE</span><h2>Worker vulnerability & exposure directory</h2><p>Illustrative synthetic profiles shown separately from environmental exposure.</p></div><span className="data-chip">SYNTHETIC DEMO ONLY</span></div>
        <div className="module-alert"><Info size={16}/>All worker profiles and sample readings are synthetic demo data. They demonstrate how environmental exposure and entered vitals can trigger explainable supervisor screening prompts; they are not real medical records, diagnoses, or validated disease predictions.</div>
        <div className="worker-health-controls">
          <input aria-label="Search worker or health domain" placeholder="Search worker ID or health domain…" value={workerSearch} onChange={e=>setWorkerSearch(e.target.value)}/>
          <select aria-label="Filter health domain" value={healthFilter} onChange={e=>setHealthFilter(e.target.value)}>
            <option value="all">All health profiles</option><option value="renal">Renal</option><option value="metabolic">Metabolic</option><option value="cardiovascular">Cardiovascular</option><option value="respiratory">Respiratory</option><option value="multi_condition">Multiple conditions</option><option value="not_provided">No profile supplied</option>
          </select>
        </div>
        {(() => {
          const profiles = (workerHealth?.profiles || []).filter(p =>
            (healthFilter==='all' || p.vulnerability_domain===healthFilter) &&
            `${p.worker_code} ${p.profile_label} ${p.vulnerability_domain}`.toLowerCase().includes(workerSearch.toLowerCase())
          );
          return <><div className="premium-metrics worker-health-metrics">
            <Metric label="DEMO WORKER PROFILES" value={workerHealth?.profiles?.length ?? '—'} sub="Synthetic examples" icon={Users}/>
            <Metric label="HIGH EXPOSURE FLAGS" value={(workerHealth?.profiles||[]).filter(p=>['high','critical'].includes(p.exposure_band)).length} sub="Environmental band only" icon={AlertTriangle}/>
            <Metric label="RENAL EXAMPLES" value={(workerHealth?.profiles||[]).filter(p=>p.vulnerability_domain==='renal').length} sub="Fictional profile labels" icon={HeartPulse}/>
            <Metric label="SAMPLE VITAL READINGS" value={workerVitals.length} sub={`${workerVitals.filter(r=>r.source==='synthetic_demo').length} synthetic demo records`} icon={Activity}/>
          </div>
          {profiles.length ? <div className="responsive-table"><table><thead><tr><th>Worker ID</th><th>Profile example</th><th>Exposure</th><th>Temperature</th><th>Humidity</th><th>Duration</th><th>Vitals</th></tr></thead><tbody>{profiles.map(p=><tr key={`${p.worker_code}-${p.vulnerability_domain}`}><td><b>{p.worker_code}</b></td><td>{p.profile_label}</td><td><span className={`status-tag ${['high','critical'].includes(p.exposure_band)?'status-high':p.exposure_band?'status-watch':'status-muted'}`}>{p.exposure_band || 'Unknown'}</span></td><td>{p.air_temperature_c!=null?`${p.air_temperature_c}°C`:'—'}</td><td>{p.relative_humidity_pct!=null?`${p.relative_humidity_pct}%`:'—'}</td><td>{p.exposure_minutes!=null?`${p.exposure_minutes} min`:'—'}</td><td>{(() => { const r=workerVitals.find(v=>v.worker_code===p.worker_code); return r ? <span className={`status-tag ${r.alert_level==='urgent'?'status-high':'status-watch'}`}>{r.alert_level} · {r.heart_rate_bpm??'—'} BPM</span> : <span className="status-tag status-muted">No reading</span> })()}</td></tr>)}</tbody></table></div> : <EmptyState title="No matching worker profiles" body={workerHealth?.notice || 'No synthetic profiles are available for this worksite.'}/>}</>;
        })()}
      </div>
      <div className="module-panel">
        <div className="panel-heading"><div><span className="eyebrow">SUPERVISOR HEALTH ALERTS</span><h2>Worker readings & medical review flags</h2><p>Sample synthetic readings are preloaded; supervisors can also enter new readings.</p></div><span className="data-chip">DEMO DATA · SCREENING ONLY</span></div>
        <div className="module-alert"><Info size={16}/>{vitalModelStatus?.model_available ? `Kaggle vital-sign baseline model is active. Validation metrics are available in backend/data/biotwin/models/kaggle_vital_risk_metrics.json. ` : `Kaggle vital-sign model is not trained in this package yet. Download the public dataset and run the two setup commands in DATASET_INTEGRATION_NOTES.md to activate High/Low dataset-label screening. `}Synthetic readings are clearly labelled and intended only to demonstrate the workflow. Alerts are conservative screening prompts, not disease predictions. Skin temperature is not core body temperature. Confirm readings, consider symptoms and device context, and use qualified medical judgement. Emergency symptoms require immediate local emergency response.</div>
        <form className="chi-form" onSubmit={submitVitals}>
          <label>Registered worker<select required value={vitalsDraft.worker_code} onChange={e=>setVitalsDraft({...vitalsDraft,worker_code:e.target.value})}><option value="">Select worker</option>{workers.map(w=><option key={w.worker_code} value={w.worker_code}>{w.worker_code}</option>)}</select></label>
          <label>Body temperature (°C)<input type="number" step="0.1" min="30" max="45" value={vitalsDraft.body_temperature_c} onChange={e=>setVitalsDraft({...vitalsDraft,body_temperature_c:e.target.value})} placeholder="e.g. 37.2"/></label>
          <label>Temperature type<select value={vitalsDraft.temperature_type} onChange={e=>setVitalsDraft({...vitalsDraft,temperature_type:e.target.value})}><option value="skin">Skin</option><option value="oral">Oral</option><option value="core">Core</option></select></label>
          <label>Heart rate (BPM)<input type="number" min="20" max="260" value={vitalsDraft.heart_rate_bpm} onChange={e=>setVitalsDraft({...vitalsDraft,heart_rate_bpm:e.target.value})} placeholder="e.g. 95"/></label>
          <label>Respiratory rate (breaths/min)<input type="number" min="4" max="80" value={vitalsDraft.respiratory_rate_bpm} onChange={e=>setVitalsDraft({...vitalsDraft,respiratory_rate_bpm:e.target.value})} placeholder="e.g. 18"/></label>
          <label>SpO₂ (%)<input type="number" min="50" max="100" step="0.1" value={vitalsDraft.spo2_pct} onChange={e=>setVitalsDraft({...vitalsDraft,spo2_pct:e.target.value})} placeholder="e.g. 98"/></label>
          <label>Systolic BP (mmHg)<input type="number" min="50" max="260" value={vitalsDraft.systolic_bp_mmhg} onChange={e=>setVitalsDraft({...vitalsDraft,systolic_bp_mmhg:e.target.value})} placeholder="e.g. 120"/></label>
          <label>Diastolic BP (mmHg)<input type="number" min="30" max="180" value={vitalsDraft.diastolic_bp_mmhg} onChange={e=>setVitalsDraft({...vitalsDraft,diastolic_bp_mmhg:e.target.value})} placeholder="e.g. 80"/></label>
          <label>Weight (kg)
            <input
              type="number"
              min="1"
              max="500"
              step="0.1"
              value={vitalsDraft.weight_kg}
              onChange={e=>setVitalsDraft({...vitalsDraft,weight_kg:e.target.value})}
              placeholder="e.g. 70"
            />
          </label>

          <label>Height (m)
            <input
              type="number"
              min="0.3"
              max="2.8"
              step="0.01"
              value={vitalsDraft.height_m}
              onChange={e=>setVitalsDraft({...vitalsDraft,height_m:e.target.value})}
              placeholder="e.g. 1.75"
            />
          </label>
          <label>Reading source<select value={vitalsDraft.source} onChange={e=>setVitalsDraft({...vitalsDraft,source:e.target.value})}><option value="manual_demo">Manual / demo entry</option><option value="wearable">Wearable device</option><option value="clinical_device">Clinical device</option></select></label>
          <label style={{gridColumn:'1 / -1'}}>Symptoms / observations<textarea rows="2" value={vitalsDraft.symptoms} onChange={e=>setVitalsDraft({...vitalsDraft,symptoms:e.target.value})} placeholder="e.g. dizziness, nausea, confusion, chest pain (if reported)"/></label>
          <button className="btn btn-dark" disabled={actionBusy || !workers.length}>Save reading & assess <ArrowRight size={15}/></button>
        </form>
        {workerVitals.length ? <div className="responsive-table"><table><thead><tr><th>Worker</th><th>Readings</th><th>Screening flag</th><th>Supervisor recommendation & AI explanation</th><th>Source</th><th>Recorded</th></tr></thead><tbody>{workerVitals.map(r=><tr key={r.id}><td><b>{r.worker_code}</b></td><td>{r.body_temperature_c!=null?`${r.body_temperature_c}°C (${r.temperature_type})`:'—'} · HR {r.heart_rate_bpm??'—'} · RR {r.respiratory_rate_bpm??'—'} · SpO₂ {r.spo2_pct??'—'}% · BP {r.systolic_bp_mmhg??'—'}/{r.diastolic_bp_mmhg??'—'}</td><td><span className={`status-tag ${r.alert_level==='urgent'?'status-high':'status-watch'}`}>{r.alert_level}</span></td><td>{r.alert_level==='urgent'?'Stop work and arrange urgent medical assessment':'Supervisor review, rest and repeat/check readings' }<small className="table-subtext">{r.alert_reason}</small>{r.dataset_vital_screening?.label ? <small className="table-subtext">Kaggle dataset-label screening: <b>{r.dataset_vital_screening.label}</b> (not a disease prediction)</small> : null}{r.ai_assessment ? <details className="evidence-full" open><summary><b>AI-generated supervisor explanation</b> <span className="status-tag status-watch">{r.ai_status==='generated'?'AI generated':r.ai_status||'AI status'}</span></summary><p style={{whiteSpace:'pre-wrap'}}>{r.ai_assessment}</p>{r.research_dataset_context?.length ? <small className="table-subtext">Research context: {r.research_dataset_context.map(s=>s.name).join(' · ')}</small> : null}</details> : <small className="table-subtext">{r.ai_status==='unavailable_no_api_key'?'AI unavailable: configure GROQ_API_KEY.':r.ai_status==='generation_error'?'AI generation failed; rule-based alert remains active.':'AI explanation pending.'}</small>}</td><td><span className={`status-tag ${r.source==='synthetic_demo'?'status-muted':'status-watch'}`}>{r.source==='synthetic_demo'?'Synthetic demo':r.source||'Unknown'}</span></td><td>{r.created_at?new Date(r.created_at).toLocaleString():'—'}</td></tr>)}</tbody></table></div> : <EmptyState title="No worker readings recorded" body="Supervisor screening flags will appear here after a reading is entered."/>}
      </div>
    </>}

    {view==='mesh' && <>
      <div className="premium-metrics"><Metric label="MESH STATUS" value={mesh?.status || '—'} sub="Backend-reported status" icon={Wifi}/><Metric label="CONNECTED" value={mesh?.connected_workers ?? mesh?.connected_devices ?? '—'} sub="Reported connected" icon={CheckCircle2}/><Metric label="UNKNOWN / OFFLINE" value={mesh?.disconnected_or_unknown ?? mesh?.unknown_devices ?? '—'} sub="Not assumed safe" icon={WifiOff}/><Metric label="QUEUED ALERTS" value={offline?.pending_alerts ?? offline?.alerts?.length ?? '—'} sub="Pending or stored alerts" icon={Zap}/></div>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">RESILIENT MONITORING</span><h2>Connectivity and device state</h2></div><span className="data-chip">NO HARDWARE CLAIMS</span></div><div className="mesh-summary-grid"><div><span>Workers reported</span><b>{mesh?.total_workers ?? mesh?.workers?.length ?? '—'}</b></div><div><span>Connected</span><b>{mesh?.connected_workers ?? mesh?.connected_devices ?? '—'}</b></div><div><span>Simulated</span><b>{mesh?.simulated_workers ?? mesh?.simulated_devices ?? '—'}</b></div><div><span>Unknown / offline</span><b>{mesh?.disconnected_or_unknown ?? mesh?.unknown_devices ?? '—'}</b></div></div>{Array.isArray(mesh?.workers) && mesh.workers.length > 0 && <div className="responsive-table"><table><thead><tr><th>Worker</th><th>Connection</th><th>Last received</th></tr></thead><tbody>{mesh.workers.map((worker,i)=><tr key={worker.worker_code || i}><td>{worker.worker_code || '—'}</td><td>{worker.connection_status || 'Unknown'}</td><td>{worker.last_data_received || '—'}</td></tr>)}</tbody></table></div>}<div className="module-alert"><Info size={16}/>This screen reports backend status only. No physical watches, smart clothing, Bluetooth or LoRa devices are assumed connected. Missing or failed signals remain unknown, never safe.</div></div>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">OFFLINE QUEUE</span><h2>Queued alerts and synchronization</h2></div><button className="btn btn-dark" disabled={!worksiteId||actionBusy} onClick={syncAlerts}><RefreshCw size={15}/> Sync queued alerts</button></div>
        {actionMessage && <div className="module-alert"><CheckCircle2 size={16}/>{actionMessage}</div>}
        <form className="chi-form" onSubmit={queueAlert}><label>Worker code (optional)<input value={alertDraft.worker_code} onChange={e=>setAlertDraft({...alertDraft,worker_code:e.target.value})} placeholder="Worker code"/></label><label>Severity<select value={alertDraft.severity} onChange={e=>setAlertDraft({...alertDraft,severity:e.target.value})}><option>low</option><option>medium</option><option>high</option><option>critical</option></select></label><label>Alert message<textarea required rows={2} value={alertDraft.message} onChange={e=>setAlertDraft({...alertDraft,message:e.target.value})} placeholder="Describe the alert to queue"/></label><button className="btn btn-dark" disabled={!worksiteId||actionBusy}>Queue offline alert <ArrowRight size={15}/></button></form>
        {(offline?.alerts||[]).length ? <div className="responsive-table"><table><thead><tr><th>Alert</th><th>Worker</th><th>Severity</th><th>Sync state</th><th>Created</th></tr></thead><tbody>{offline.alerts.map(a=><tr key={a.id}><td>{a.message}</td><td>{a.worker_code||'—'}</td><td>{a.severity}</td><td>{a.sync_status}</td><td>{a.created_at ? new Date(a.created_at).toLocaleString() : '—'}</td></tr>)}</tbody></table></div> : <EmptyState title="No queued alerts" body={offline?.notice || 'No offline alerts have been recorded for this worksite.'}/>}
      </div>
    </>}

    {view==='preventive' && <>
      <div className="premium-metrics"><Metric label="INTERVENTIONS" value={interventions.length} sub="Recorded actions" icon={ShieldCheck}/><Metric label="RECOMMENDED" value={interventions.filter(x=>x.status==='recommended').length} sub="Awaiting review" icon={AlertTriangle}/><Metric label="APPROVED" value={interventions.filter(x=>x.status==='approved').length} sub="Supervisor approved" icon={CheckCircle2}/><Metric label="COMPLETED" value={interventions.filter(x=>x.status==='completed').length} sub="Recorded completion" icon={Activity}/></div>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">PREVENTIVE ACTIONS</span><h2>Intervention register</h2></div><span className="data-chip">SUPERVISOR REVIEW</span></div>
        {actionMessage && <div className="module-alert"><CheckCircle2 size={16}/>{actionMessage}</div>}
        <form className="chi-form" onSubmit={addIntervention}><label>Action type<select value={interventionDraft.intervention_type} onChange={e=>setInterventionDraft({...interventionDraft,intervention_type:e.target.value})}><option value="rest_break">Rest break</option><option value="task_rotation">Task rotation</option><option value="shade_transition">Move to shade</option><option value="work_pause">Pause work</option><option value="hydration_reminder">Hydration reminder</option></select></label><label>Zone (optional)<select value={interventionDraft.zone_id} onChange={e=>setInterventionDraft({...interventionDraft,zone_id:e.target.value})}><option value="">No zone selected</option>{zones.map(z=><option key={z.id} value={z.id}>{z.name}</option>)}</select></label><label>Affected crew count<input type="number" min="0" value={interventionDraft.affected_crew_count} onChange={e=>setInterventionDraft({...interventionDraft,affected_crew_count:e.target.value})}/></label><label>Reason<textarea required minLength={5} rows={2} value={interventionDraft.reason} onChange={e=>setInterventionDraft({...interventionDraft,reason:e.target.value})} placeholder="Record why this preventive action is recommended"/></label><button className="btn btn-dark" disabled={!worksiteId||actionBusy}>Add for supervisor review <ArrowRight size={15}/></button></form>
      {!interventions.length ? <EmptyState title="No interventions recorded" body="Recommendations and approved actions will appear here when entered through the intervention workflow."/> :
      <div className="responsive-table"><table><thead><tr><th>Action</th><th>Reason</th><th>Status</th><th>Affected crew</th><th>Worksite</th><th>Supervisor action</th></tr></thead><tbody>{interventions.map((x,i)=><tr key={x.id||i}><td><b>{String(x.intervention_type||'').replaceAll('_',' ')}</b></td><td>{x.reason}</td><td><span className="status-tag status-watch">{x.status}</span></td><td>{x.affected_crew_count ?? '—'}</td><td>{siteName(x.worksite_id)}</td><td><div className="action-row">{x.status==='recommended' && <button className="text-btn" disabled={actionBusy} onClick={()=>changeIntervention(x.id,'approved')}>Approve</button>}{x.status==='approved' && <button className="text-btn" disabled={actionBusy} onClick={()=>changeIntervention(x.id,'completed')}>Mark complete</button>}{['recommended','approved'].includes(x.status) && <button className="text-btn" disabled={actionBusy} onClick={()=>changeIntervention(x.id,'dismissed')}>Dismiss</button>}</div></td></tr>)}</tbody></table></div>}</div>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">PREVENTION GUIDANCE</span><h2>Core workplace controls</h2></div></div><div className="insight-grid"><div><ShieldCheck/><b>Reduce exposure</b><p>Use work/rest planning, shade and cooling measures appropriate to the worksite.</p></div><div><Activity/><b>Monitor workers</b><p>Train workers and supervisors to recognize early heat-illness symptoms and report concerns.</p></div><div><Users/><b>Human review</b><p>Escalate concerning symptoms and involve qualified occupational-health professionals.</p></div></div></div>
    </>}

    {view==='analytics' && <>
      <div className="premium-metrics"><Metric label="WORKERS" value={workers.length} sub="Registered records" icon={Users}/><Metric label="WORKSITES" value={sites.length} sub="Registered records" icon={Database}/><Metric label="EXPOSURE RECORDS" value={exposures.length} sub="Recorded entries" icon={Activity}/><Metric label="INTERVENTIONS" value={interventions.length} sub="Recorded actions" icon={ShieldCheck}/></div>
      <div className="module-panel"><div className="panel-heading"><div><span className="eyebrow">DATA QUALITY</span><h2>Evidence and record completeness</h2></div><a className="btn btn-dark" download="heatshield-operational-records.csv" href={`data:text/csv;charset=utf-8,${encodeURIComponent(['record_type,worker_code,worksite_id,recorded_at,source,exposure_minutes,air_temperature_c,measured_wbgt_c,risk_level,intervention_status','' + exposures.map(x=>['exposure',x.worker_code||'',x.worksite_id||'',x.recorded_at||'',x.source||'',x.exposure_minutes??'',x.air_temperature_c??'',x.measured_wbgt_c??'',x.risk_level||'',''].map(v=>`"${String(v).replaceAll('"','""')}"`).join(',')).join('\n')].filter(Boolean).join('\n'))}`}>Export CSV</a></div><div className="insight-grid"><div><b>{measured.length}</b><p>On-site measured WBGT records</p></div><div><b>{exposures.filter(x=>x.source==='demo_simulation').length}</b><p>Explicitly labelled demo exposure records</p></div><div><b>{stale.length}</b><p>Exposure records older than 24 hours</p></div></div><div className="module-alert"><Info size={16}/>These are record counts, not population health statistics or clinical outcome rates. Missing data is not interpreted as a safe exposure or a healthy worker.</div><h3>Exposure records by date</h3>{Object.entries(exposures.reduce((acc,x)=>{const d=x.recorded_at?new Date(x.recorded_at).toLocaleDateString():'Unknown date';acc[d]=(acc[d]||0)+1;return acc},{})).sort((a,b)=>new Date(a[0])-new Date(b[0])).map(([d,n])=><div className="data-bar-row" key={d}><span>{d}</span><div className="data-bar-track"><div className="data-bar-fill" style={{width:`${Math.max(3,n/Math.max(1,exposures.length)*100)}%`}}/></div><b>{n}</b></div>)}</div>
    </>}
  </section>
}
