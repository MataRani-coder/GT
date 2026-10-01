import React, { createContext, useContext, useEffect, useState } from 'react';
import auth from '../services/auth';
import axios from 'axios';

const AuthContext = createContext(null);
const API = '/api';

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(auth.getUser());
  const [loading, setLoading] = useState(Boolean(auth.getToken()));

  useEffect(() => {
    const expired = () => { auth.clear(); setUser(null); };
    window.addEventListener('ghost-trail-auth-expired', expired);
    const token = auth.getToken();
    if (!token) { setLoading(false); return; }
    axios.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => { auth.setSession(token, r.data.user); setUser(r.data.user); })
      .catch(() => { auth.clear(); setUser(null); })
      .finally(() => setLoading(false));
    return () => window.removeEventListener('ghost-trail-auth-expired', expired);
  }, []);

  const login = async (username, password) => {
    const response = await axios.post(`${API}/auth/login`, { username, password });
    auth.setSession(response.data.token, response.data.user);
    setUser(response.data.user);
    return response.data;
  };

  const logout = () => { auth.clear(); setUser(null); };

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>;
};

export const useAuth = () => useContext(AuthContext);
