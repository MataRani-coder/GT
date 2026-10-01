import React, { useEffect, useState } from 'react';
import { ShieldCheck, LockKeyhole, LogIn, AlertTriangle, Loader2 } from 'lucide-react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const AUTH_TIMEOUT_MS = 10000;

export default function LoginPage() {
  const { login, user, loading } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && user) navigate('/dashboard', { replace: true });
  }, [loading, user, navigate]);

  const submit = async e => {
    e.preventDefault();
    if (busy) return;
    setError('');
    if (!username.trim() || !password) {
      setError('Enter both username and password.');
      return;
    }
    setBusy(true);
    try {
      await login(username.trim(), password);
      // Login succeeded. Explicitly leave /login; otherwise the /login route
      // remains mounted and the user sees the form reset with no navigation.
      navigate('/dashboard', { replace: true });
    } catch (err) {
      if (err?.code === 'ECONNABORTED') {
        setError(`Authentication timed out after ${AUTH_TIMEOUT_MS / 1000}s. Check that Ghost Trail is running.`);
      } else if (!err?.response) {
        setError('Cannot reach Ghost Trail server at 127.0.0.1:8765.');
      } else {
        setError(err?.response?.data?.detail || `Authentication failed (${err.response.status}).`);
      }
    } finally {
      setBusy(false);
    }
  };

  if (!loading && user) return <Navigate to="/dashboard" replace />;

  return <div className="min-h-screen bg-[#05080c] text-slate-200 flex items-center justify-center p-6 font-mono">
    <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-[#0b1118] p-7 shadow-2xl">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-11 h-11 rounded-xl bg-cyan-400/10 border border-cyan-400/30 flex items-center justify-center"><ShieldCheck className="text-cyan-300" /></div>
        <div><div className="text-lg font-bold tracking-widest uppercase">Ghost Trail</div><div className="text-[10px] text-slate-500 tracking-[.25em]">SECURE OPERATOR ACCESS</div></div>
      </div>
      <form onSubmit={submit} className="space-y-4">
        <label className="block text-xs text-slate-400">USERNAME<input value={username} onChange={e=>setUsername(e.target.value)} className="mt-2 w-full rounded-lg bg-black/30 border border-slate-700 px-3 py-3 text-sm outline-none focus:border-cyan-400" autoComplete="username" /></label>
        <label className="block text-xs text-slate-400">PASSWORD<div className="relative"><LockKeyhole size={15} className="absolute left-3 top-3.5 text-slate-600"/><input type="password" value={password} onChange={e=>setPassword(e.target.value)} className="mt-2 w-full rounded-lg bg-black/30 border border-slate-700 pl-9 pr-3 py-3 text-sm outline-none focus:border-cyan-400" autoComplete="current-password" /></div></label>
        {error && <div className="flex gap-2 items-start rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-300"><AlertTriangle size={15}/>{error}</div>}
        <button type="submit" disabled={busy} className="w-full flex items-center justify-center gap-2 rounded-lg bg-cyan-400 text-black font-bold py-3 text-xs tracking-widest disabled:opacity-50 disabled:cursor-wait hover:bg-cyan-300 transition-colors">{busy ? <Loader2 size={15} className="animate-spin"/> : <LogIn size={15}/>} {busy ? 'AUTHENTICATING...' : 'AUTHENTICATE'}</button>
      </form>
      <p className="mt-6 text-[10px] leading-5 text-slate-600">Access is role-controlled. Administrator bootstrap credentials are generated on first server start unless GHOST_TRAIL_ADMIN_PASSWORD is configured.</p>
    </div>
  </div>;
}
