import React, { useEffect, useState } from 'react';
import { Activity, BrainCircuit, Search, ShieldCheck, Trash2 } from 'lucide-react';
import apiService from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function InvestigatorPage() {
  const { user } = useAuth();
  const [query, setQuery] = useState('Investigate the most recent high-risk track.');
  const [result, setResult] = useState(null);
  const [cases, setCases] = useState([]);
  const [privacy, setPrivacy] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setError('');
    const [caseData, privacyData] = await Promise.all([
      apiService.getInvestigationCases(),
      apiService.getPrivacyLedger(),
    ]);
    if (caseData) setCases(caseData);
    if (privacyData) setPrivacy(privacyData);
  };

  useEffect(() => { load(); }, []);

  const runInvestigation = async () => {
    if (!query.trim()) return;
    setBusy(true); setError('');
    try {
      const data = await apiService.runInvestigation(query.trim());
      if (!data) throw new Error('Investigator unavailable');
      setResult(data);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Investigation failed');
    } finally { setBusy(false); }
  };

  const purge = async () => {
    if (user?.role !== 'admin') return;
    const data = await apiService.purgePrivacy();
    if (data) await load();
  };

  return (
    <div className="page-shell" style={{maxWidth: 1200, margin: '0 auto', padding: '28px'}}>
      <div style={{display:'flex',justifyContent:'space-between',gap:20,alignItems:'flex-start',marginBottom:24}}>
        <div>
          <div style={{fontSize:11,letterSpacing:'.18em',color:'#64748b',fontFamily:'monospace'}}>ANALYST WORKBENCH</div>
          <h1 style={{fontSize:30,fontWeight:700,margin:'6px 0'}}>Investigator</h1>
          <p style={{color:'#94a3b8',maxWidth:760}}>Tool-using investigation over structured telemetry. Raw video and biometric embeddings are not exposed to the agent.</p>
        </div>
        <div style={{display:'flex',gap:8,alignItems:'center',fontFamily:'monospace',fontSize:11}}>
          <BrainCircuit size={16}/>{result?.llm ? 'CLAUDE TOOL-USE' : 'OFFLINE TOOL MODE'}
        </div>
      </div>

      <div style={{display:'grid',gridTemplateColumns:'minmax(0,1.5fr) minmax(300px,1fr)',gap:18}}>
        <section className="panel" style={{padding:18}}>
          <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:12}}><Search size={16}/><b>Investigation query</b></div>
          <textarea value={query} onChange={e=>setQuery(e.target.value)} rows={4} style={{width:'100%',background:'#0b1118',border:'1px solid #263344',borderRadius:8,padding:12,color:'#e2e8f0',resize:'vertical'}} />
          <button className="yellow-button" onClick={runInvestigation} disabled={busy} style={{marginTop:12}}>{busy ? 'INVESTIGATING…' : 'RUN INVESTIGATION'}</button>
          {error && <div style={{marginTop:12,color:'#fca5a5',fontFamily:'monospace',fontSize:12}}>{error}</div>}
          {result && <div style={{marginTop:18,padding:14,background:'#0a1017',borderRadius:8,border:'1px solid #1e293b'}}>
            <div style={{fontSize:11,color:'#64748b',fontFamily:'monospace',marginBottom:8}}>EVIDENCE SUMMARY</div>
            <div style={{whiteSpace:'pre-wrap',lineHeight:1.6}}>{result.answer}</div>
            <div style={{marginTop:12,fontSize:11,color:'#94a3b8'}}>Tools: {(result.tools_used || []).join(', ') || 'none'}</div>
          </div>}
        </section>

        <section className="panel" style={{padding:18}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
            <div style={{display:'flex',alignItems:'center',gap:8}}><ShieldCheck size={16}/><b>Privacy ledger</b></div>
            {user?.role === 'admin' && <button className="top-icon-btn" onClick={purge} title="Run retention purge"><Trash2 size={14}/></button>}
          </div>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10,marginTop:16}}>
            <Metric label="Sightings" value={privacy?.total_sightings ?? '—'} />
            <Metric label="Face escalations" value={privacy?.face_escalations ?? '—'} />
            <Metric label="Anonymous rate" value={privacy ? `${privacy.anonymity_rate}%` : '—'} />
            <Metric label="Ledger events" value={privacy?.privacy_events ?? '—'} />
          </div>
          <div style={{marginTop:16,fontSize:11,color:'#64748b',fontFamily:'monospace'}}>RETENTION: {privacy?.sighting_retention_hours ?? '—'}h sightings · {privacy?.flagged_retention_hours ?? '—'}h review captures</div>
        </section>
      </div>

      <section className="panel" style={{padding:18,marginTop:18}}>
        <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:14}}><Activity size={16}/><b>Case files</b></div>
        {cases.length === 0 ? <div style={{color:'#64748b'}}>No investigation cases yet.</div> : cases.map(c => (
          <div key={c.id} style={{padding:'12px 0',borderTop:'1px solid #172130'}}>
            <div style={{display:'flex',justifyContent:'space-between',gap:12}}><b>{c.title}</b><span style={{fontFamily:'monospace',fontSize:10,color:'#94a3b8'}}>{String(c.severity).toUpperCase()}</span></div>
            <div style={{marginTop:5,color:'#94a3b8',fontSize:13}}>{c.summary}</div>
          </div>
        ))}
      </section>
    </div>
  );
}

function Metric({label,value}) {
  return <div style={{padding:12,background:'#0b1118',border:'1px solid #1e293b',borderRadius:8}}><div style={{fontSize:10,color:'#64748b',fontFamily:'monospace'}}>{label.toUpperCase()}</div><div style={{fontSize:22,fontWeight:700,marginTop:4}}>{value}</div></div>;
}
