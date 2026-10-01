import axios from 'axios';
import auth from './auth';

// Use relative /api so it works both in the .exe (served by FastAPI)
// and in dev mode (Vite proxies /api → http://127.0.0.1:8765)
const BASE_URL = '/api';
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

const secureMediaUrl = (url) => {
  if (!url || !url.startsWith('/api/')) return url;
  const token = auth.getToken();
  if (!token) return url;
  return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`;
};

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 45000,
  headers: {
    'Content-Type': 'application/json',
  }
});

api.interceptors.request.use(config => {
  const token = auth.getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(r => r, error => {
  if (error?.response?.status === 401) { auth.clear(); window.dispatchEvent(new Event('ghost-trail-auth-expired')); }
  return Promise.reject(error);
});

// High-fidelity fallback database for standalone demo/testing
let mockPersons = [
  { id: 1, name: 'Ganesh', face_review_status: 'pending', status: 'Authorized', clearance: 'Level 4 (Director)', last_seen: new Date(Date.now() - 2 * 60000).toISOString(), camera: 'cam_1', confidence: 0.94, thumbnail: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=300&auto=format&fit=crop&q=80' },
  { id: 2, name: 'Lakshya', face_review_status: 'confirmed', status: 'Authorized', clearance: 'Level 3 (Security Officer)', last_seen: new Date(Date.now() - 8 * 60000).toISOString(), camera: 'cam_2', confidence: 0.91, thumbnail: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=300&auto=format&fit=crop&q=80' },
  { id: 3, name: 'Ansh', face_review_status: 'pending', status: 'Authorized', clearance: 'Level 2 (Personnel)', last_seen: new Date(Date.now() - 35 * 60000).toISOString(), camera: 'cam_1', confidence: 0.88, thumbnail: 'https://images.unsplash.com/photo-1492562080023-ab3db95bfbce?w=300&auto=format&fit=crop&q=80' },
  { id: 4, name: 'Arnav', face_review_status: 'denied', status: 'Restricted', risk_tier: 'high_risk', clearance: 'Level 1 (Contractor)', last_seen: new Date(Date.now() - 90 * 60000).toISOString(), camera: 'cam_3', confidence: 0.82, thumbnail: 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=300&auto=format&fit=crop&q=80' },
  { id: 5, name: 'Ashwini', face_review_status: 'pending', status: 'Authorized', clearance: 'Level 3 (Analyst)', last_seen: new Date(Date.now() - 140 * 60000).toISOString(), camera: 'cam_2', confidence: 0.89, thumbnail: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=300&auto=format&fit=crop&q=80' }
];

let mockAlerts = [
  { id: 'face-denied-900', incident_id: 900, source: 'manual_face_review', person_id: 4, person_name: 'Arnav', alert_type: 'face_verification_denied', type: 'face_verification_denied', camera_id: 'PERSONS_DB', message: 'Face Verification Denied — High Risk Person', detail: 'Manual face verification was denied for enrolled profile Arnav (ID #4). The profile has been escalated to the High Risk category for security review.', risk_tier: 'high_risk', timestamp: Date.now() / 1000 - 60, status: 'active', severity: 'critical' },
  { id: 'alt-001', alert_type: 'unknown_person', type: 'unknown_person', camera_id: 'cam_2', message: 'Unidentified Person Detected in Restricted Zone', detail: 'Target matched temporary profile Guest_882 with 0.84 face distance threshold breach.', timestamp: Date.now() / 1000 - 120, status: 'active', severity: 'critical' },
  { id: 'alt-002', alert_type: 'contextual_object', type: 'contextual_object', camera_id: 'cam_1', message: 'Contextual Object Alert — BACKPACK', detail: 'Backpack remained stationary without a nearby person for the configured duration.', timestamp: Date.now() / 1000 - 450, status: 'active', severity: 'warning' },
  { id: 'alt-003', alert_type: 'unknown_person', type: 'unknown_person', camera_id: 'cam_3', message: 'After-hours Movement in Server Vault', detail: 'Rapid motion trigger by unregistered individual without active badge beacon.', timestamp: Date.now() / 1000 - 1200, status: 'dismissed', severity: 'high' }
];

let mockSettings = {
  object_monitoring: { monitored_classes: [2, 24, 26, 28], contextual_alert_classes: [24, 26, 28], unattended_sec: 10.0, stationary_speed_px_sec: 18.0, person_proximity_ratio: 1.5, alert_cooldown_sec: 30.0 },
  display_duration_sec: 15.0,
  confidence_threshold: 0.40,
  reid_threshold: 0.75,
  confirm_frames: 4,
  storage_path: 'C:/GhostTrail/recordings',
  retention_days: 14,
  cameras: [
    { camera_id: 'cam_1', name: 'Main Lobby & Reception', source: '0', enabled: true, zone: 'Zone A - Entrance', online: true, fps: 28.4 },
    { camera_id: 'cam_2', name: 'East Perimeter & Alley', source: 'rtsp://192.168.1.120:554/ch0', enabled: true, zone: 'Zone B - Exterior', online: true, fps: 24.1 },
    { camera_id: 'cam_3', name: 'Server Vault & Labs', source: 'rtsp://192.168.1.121:554/ch0', enabled: true, zone: 'Zone C - Restricted', online: true, fps: 30.0 },
    { camera_id: 'cam_4', name: 'Loading Dock & Bay 2', source: 'rtsp://192.168.1.122:554/ch0', enabled: false, zone: 'Zone D - Logistics', online: false, fps: 0.0 }
  ]
};

// Mock data is available only in explicit demo mode. Production mode never
// turns a backend failure into believable-looking synthetic data.
const handleRequest = async (requestPromise, mockFallback) => {
  try {
    const response = await requestPromise;
    return response.data;
  } catch (error) {
    if (DEMO_MODE) {
      return typeof mockFallback === 'function' ? mockFallback() : mockFallback;
    }

    console.error('[Ghost Trail API] Backend unavailable:', error?.message || error);
    return null;
  }
};

export const apiService = {
  // Exclusive webcam sessions: release the backend OpenCV webcam before
  // browser getUserMedia() acquires the same physical device.
  // Camera ownership is safety-critical: never report a fake successful session
  // when the backend is unavailable, otherwise OpenCV may still own the device.
  startCameraSession: () => handleRequest(api.post('/camera/session/start'), () => null),
  stopCameraSession: () => handleRequest(api.post('/camera/session/stop'), () => null),

  // Live room/environment reconstruction
  resetEnvironmentScan: () => handleRequest(api.post('/environment/scan/reset'), () => ({ success: true, status: 'ready' })),
  scanEnvironmentFrame: async (blob) => {
    const formData = new FormData();
    formData.append('frame', blob, 'room-scan.jpg');
    try {
      const response = await api.post('/environment/scan/frame', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 15000,
      });
      return response.data;
    } catch (error) {
      if (DEMO_MODE) return null;
      console.error('[Ghost Trail Environment Scan]', error?.message || error);
      return null;
    }
  },

  // Cameras
  getCameras: () => 
    handleRequest(api.get('/cameras'), () => mockSettings.cameras),
    
  toggleCamera: (cameraId, enabled) => 
    handleRequest(api.post(`/cameras/${cameraId}/toggle`, { enabled }), () => {
      const cam = mockSettings.cameras.find(c => c.camera_id === cameraId);
      if (cam) cam.enabled = enabled;
      return { success: true, cameras: mockSettings.cameras };
    }),

  addCamera: (cameraData) =>
    handleRequest(api.post('/cameras', cameraData), () => {
      const newCam = {
        camera_id: cameraData.camera_id || `cam_${mockSettings.cameras.length + 1}`,
        name: cameraData.name || 'New Camera Feed',
        source: cameraData.source || '0',
        enabled: true,
        zone: cameraData.zone || 'Zone A',
        online: true,
        fps: 25.0
      };
      mockSettings.cameras.push(newCam);
      return { success: true, camera: newCam };
    }),

  removeCamera: (cameraId) =>
    handleRequest(api.delete(`/cameras/${cameraId}`), () => {
      mockSettings.cameras = mockSettings.cameras.filter(c => c.camera_id !== cameraId);
      return { success: true, camera_id: cameraId };
    }),

  // Detections & System Summary
  getDetectionsSummary: () =>
    handleRequest(api.get('/dashboard'), () => ({
      activeCameras: mockSettings.cameras.filter(c => c.enabled).length,
      totalDetections: 48,
      activeAlerts: mockAlerts.filter(a => a.status === 'active').length,
      systemHealth: 99.4,
      aiModel: 'YOLOv8x + OSNet Re-ID',
      fps: 29.2,
      latencyMs: 14.8
    })),

  getStats: () =>
    handleRequest(api.get('/stats'), () => ({
      timelineData: [],
      cameraData: [],
      totalSightings: 0,
      authorizedDetections: 0,
      unknownGuests: 0,
      highRiskDetections: 0,
      averageConfidence: null,
    })),

  getBehaviorRules: () => handleRequest(api.get('/behavior-rules'), () => null),

  // Registered Persons
  getRegisteredPersons: () =>
    handleRequest(api.get('/persons'), () => mockPersons).then(data => (data || []).map(p => ({ ...p, thumbnail: secureMediaUrl(p.thumbnail) }))),

  registerPerson: (name, imageFile, force = false, updateId = null) => {
    const formData = new FormData();
    formData.append('name', name);
    if (imageFile) formData.append('image', imageFile);
    if (force) formData.append('force', 'true');
    if (updateId) formData.append('update_id', updateId);
    
    return handleRequest(
      api.post('/persons', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      }),
      () => {
        // Fallback simulation
        const newId = mockPersons.length + 1;
        const newPerson = {
          id: newId,
          name: name,
          status: 'Authorized',
          clearance: 'Level 2 (Personnel)',
          last_seen: new Date().toISOString(),
          camera: 'cam_1',
          confidence: 0.95,
          thumbnail: imageFile instanceof Blob ? URL.createObjectURL(imageFile) : 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=300&auto=format&fit=crop&q=80'
        };
        mockPersons.unshift(newPerson);
        return { success: true, person: newPerson };
      }
    );
  },

  updatePersonDetails: (id, details) =>
    handleRequest(api.put(`/persons/${id}`, details), () => {
      const person = mockPersons.find(p => p.id === id);
      if (person) Object.assign(person, details);
      return { success: true, id, ...details };
    }),

  reviewPersonFace: (id, status, note = '') =>
    handleRequest(api.post(`/persons/${id}/face-review`, { status, note }), () => {
      const person = mockPersons.find(p => p.id === id);
      if (person) {
        person.face_review_status = status;
        person.face_reviewed_ts = Date.now();
        person.face_review_note = note || null;
        if (status === 'denied') {
          person.risk_tier = 'high_risk';
          person.status = 'Restricted';
          const existing = mockAlerts.find(a => a.person_id === id && a.type === 'face_verification_denied' && a.status === 'active');
          if (!existing) {
            mockAlerts.unshift({
              id: `face-denied-${Date.now()}`,
              incident_id: Date.now(),
              source: 'manual_face_review',
              person_id: id,
              person_name: person.name,
              alert_type: 'face_verification_denied',
              type: 'face_verification_denied',
              camera_id: 'PERSONS_DB',
              message: 'Face Verification Denied — High Risk Person',
              detail: `Manual face verification was denied for enrolled profile ${person.name} (ID #${id}). The profile has been escalated to the High Risk category for security review.`,
              risk_tier: 'high_risk',
              timestamp: Date.now() / 1000,
              status: 'active',
              severity: 'critical'
            });
          }
        } else {
          person.risk_tier = null;
          person.status = 'Authorized';
          mockAlerts = mockAlerts.map(a => a.person_id === id && a.type === 'face_verification_denied' ? { ...a, status: 'dismissed' } : a);
        }
      }
      return { success: true, person_id: id, status };
    }),

  deletePerson: (id) =>
    handleRequest(api.delete(`/persons/${id}`), () => {
      mockPersons = mockPersons.filter(p => p.id !== id);
      return { success: true, id };
    }),

  unenrollPerson: (id) =>
    handleRequest(api.post(`/persons/${id}/unenroll`), () => {
      mockPersons = mockPersons.filter(p => p.id !== id);
      return { success: true, id, status: 'unenrolled' };
    }),

  // Flagged persons — pending-review captures from the anomaly/behavior
  // pipeline. Nothing here is a confirmed "suspicious" tag until a human
  // reviews the photo via confirmFlaggedPerson/dismissFlaggedPerson.
  getFlaggedPersons: () =>
    handleRequest(api.get('/persons/flagged', { params: { status: 'pending_review' } }), () => []).then(data => (data || []).map(p => ({ ...p, thumbnail: secureMediaUrl(p.thumbnail) }))),

  confirmFlaggedPerson: (id) =>
    handleRequest(api.post(`/persons/flagged/${id}/confirm`), () => {
      const accepted = mockAlerts.find(a => String(a.incident_id || a.id) === String(id));
      const flag = {
        id,
        status: 'confirmed'
      };
      return {
        ...flag,
        success: true,
        message: 'face has been accepted, person has been added to the database',
        incident: accepted || {
          id: `face-accepted-${Date.now()}`,
          incident_id: Date.now(),
          type: 'face_verification_accepted',
          alert_type: 'face_verification_accepted',
          message: 'face has been accepted, person has been added to the database',
          detail: 'The accepted person has been added to the enrolled face database.',
          risk_tier: 'verified',
          timestamp: Date.now() / 1000,
          status: 'active',
          severity: 'info'
        }
      };
    }),

  denyFlaggedPerson: (id) =>
    handleRequest(api.post(`/persons/flagged/${id}/deny`), () => ({ success: true, id, status: 'denied', risk_tier: 'high_risk' })),

  dismissFlaggedPerson: (id) =>
    handleRequest(api.delete(`/persons/flagged/${id}`), () => ({ success: true, id })),

  // Sightings
  getSightings: () =>
    handleRequest(api.get('/sightings'), () => []),

  // Alerts
  getAlerts: () =>
    handleRequest(api.get('/alerts'), () => mockAlerts),

  dismissAlert: (alertId) =>
    handleRequest(api.post(`/alerts/${alertId}/dismiss`), () => {
      mockAlerts = mockAlerts.map(a => (String(a.id) === String(alertId) || String(a.timestamp) === String(alertId)) ? { ...a, status: 'dismissed' } : a);
      return { success: true, alert_id: alertId };
    }),

  clearAllAlerts: () =>
    handleRequest(api.delete('/alerts'), () => {
      mockAlerts = [];
      return { success: true };
    }),

  // Investigator + privacy
  getInvestigationCases: () => handleRequest(api.get('/investigator/cases'), () => []),
  runInvestigation: (query) => handleRequest(api.post('/investigator/query', { query }), () => null),
  getPrivacyLedger: () => handleRequest(api.get('/privacy/ledger'), () => ({ total_sightings: 0, face_escalations: 0, privacy_events: 0, anonymity_rate: 100, event_counts: {}, recent_events: [] })),
  purgePrivacy: () => handleRequest(api.post('/privacy/purge'), () => ({ success: true })),

  // System Settings
  getSystemSettings: () =>
    handleRequest(api.get('/config'), () => mockSettings),

  updateSystemSettings: (newSettings) =>
    handleRequest(api.post('/config', { data: newSettings }), () => {
      mockSettings = { ...mockSettings, ...newSettings };
      return { ok: true, settings: mockSettings };
    }),

  // Health check / System telemetry
  getSystemHealth: () =>
    handleRequest(api.get('/status'), () => ({
      status: 'running',
      fps: 29.4,
      cameras: ['cam_1', 'cam_2', 'cam_3'],
      active_alerts: mockAlerts.filter(a => a.status === 'active').length,
      uptime: '3d 14h 22m',
      system: 'YOLOv8 + DeepReID OSNet (Ghost Trail Core)',
      gpu_status: 'NVIDIA RTX Core (CUDA 12.2)',
      gpu_temp: '58°C',
      vram_usage: '2.4 GB / 8.0 GB (30%)',
      cpu_usage: '18%',
      memory_usage: '4.2 GB / 16.0 GB (26%)',
      inference_time: '12.4 ms',
      reid_latency: '6.1 ms',
      storage_free: '482 GB / 1000 GB'
    }))
};

export default apiService;
