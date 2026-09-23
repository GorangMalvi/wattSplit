import { Capacitor } from '@capacitor/core';
import axios from 'axios';
import { supabase } from './supabase';

// Same-origin by default: Vite (dev) and nginx (Docker) both proxy /api.
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Household the dashboard is working in; sent as X-Household-Id.
let activeHouseholdId = null;

export const setActiveHousehold = (id) => {
  activeHouseholdId = id;
};

api.interceptors.request.use(async (config) => {
  // getSession() refreshes the access token when it is about to expire.
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  if (activeHouseholdId) config.headers['X-Household-Id'] = activeHouseholdId;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Session is no longer valid: sign out so the login screen shows.
      supabase.auth.signOut();
    }
    const detail = error.response?.data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg).join('; ')
      : detail || error.message || 'Something went wrong';
    const err = new Error(message);
    err.status = error.response?.status;
    return Promise.reject(err);
  }
);

// Households
export const getHouseholds = () => api.get('/households').then((res) => res.data);

export const createHousehold = (name) =>
  api.post('/households', { name }).then((res) => res.data);

export const joinHousehold = (inviteCode) =>
  api.post('/households/join', { invite_code: inviteCode }).then((res) => res.data);

// Months
export const getMonths = () => api.get('/months').then((res) => res.data);

export const getMonth = (month) => api.get(`/months/${month}`).then((res) => res.data);

export const createMonth = (payload) => api.post('/months', payload).then((res) => res.data);

export const updateMonth = (month, payload) =>
  api.put(`/months/${month}`, payload).then((res) => res.data);

// Roommates
export const getRoommates = () => api.get('/roommates').then((res) => res.data);

export const createRoommate = (payload) =>
  api.post('/roommates', payload).then((res) => res.data);

export const updateRoommate = (id, payload) =>
  api.put(`/roommates/${id}`, payload).then((res) => res.data);

// Owner: invite someone by email to be this roommate. Returns the invite with
// its link/code and whether the email went out (email_sent, email_error).
export const inviteRoommate = (roommateId, email) =>
  api.post(`/roommates/${roommateId}/invite`, { email }).then((res) => res.data);

export const getInvites = () => api.get('/invites').then((res) => res.data);

export const revokeInvite = (id) => api.delete(`/invites/${id}`);

// No sign-in needed: who the invite is for (household, roommate, email).
export const lookupInvite = (code) =>
  api.get(`/invites/lookup/${encodeURIComponent(code)}`).then((res) => res.data);

export const acceptInvite = (code) =>
  api.post('/invites/accept', { code }).then((res) => res.data);

// Owner only: detach the login linked to a roommate
export const unlinkRoommate = (id) => api.delete(`/roommates/${id}/link`);

// The signed-in user: role, linked roommate, personal dashboard
export const getMe = () => api.get('/me').then((res) => res.data);

// payload: { roommate_id } to pick an existing roommate, or { name } to add yourself
export const linkMyRoommate = (payload) =>
  api.post('/me/roommate', payload).then((res) => res.data);

export const unlinkMyRoommate = () => api.delete('/me/roommate');

export const getMyDashboard = () => api.get('/me/dashboard').then((res) => res.data);

// Owner: the meter provider's Monthly Consumption Report (.xlsx), sent as the
// raw body. dryRun: only preview what would be imported.
export const uploadMeterReport = (file, { dryRun }) =>
  api
    .post('/meter-report', file, {
      params: { dry_run: dryRun },
      headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      },
    })
    .then((res) => res.data);

// Calculated split + balances for a month
export const getCalculate = (month) =>
  api.get(`/calculate/${month}`).then((res) => res.data);

// Running balances across all months
export const getHistory = () => api.get('/history').then((res) => res.data);

// Readings
// fields: { current_reading, start_reading } (either or both; null clears).
// A plain number means the month-end reading.
export const updateReading = (month, roommateId, fields) =>
  api
    .put(
      `/readings/${month}/${roommateId}`,
      typeof fields === 'number' ? { current_reading: fields } : fields
    )
    .then((res) => res.data);

export const deleteReading = (month, roommateId) => api.delete(`/readings/${month}/${roommateId}`);

// Recharges
export const getRecharges = (month) =>
  api.get('/recharges', { params: { month } }).then((res) => res.data);

export const createRecharge = (payload) =>
  api.post('/recharges', payload).then((res) => res.data);

export const updateRecharge = (id, payload) =>
  api.put(`/recharges/${id}`, payload).then((res) => res.data);

export const deleteRecharge = (id) =>
  api.delete(`/recharges/${id}`).then((res) => res.data);

const blobToBase64 = (blob) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });

// Android: WebViews can't download, so save to the cache and open the share sheet.
const shareOnDevice = async (blob, filename) => {
  const [{ Filesystem, Directory }, { Share }] = await Promise.all([
    import('@capacitor/filesystem'),
    import('@capacitor/share'),
  ]);
  const { uri } = await Filesystem.writeFile({
    path: filename,
    data: await blobToBase64(blob),
    directory: Directory.Cache,
  });
  await Share.share({ title: filename, files: [uri] });
};

// Export: fetched with auth headers, then saved via a temporary link.
export const downloadExport = async (month) => {
  const res = await api.get(`/export/${month}`, { responseType: 'blob' });
  const filename = `${month}_report.xlsx`;
  if (Capacitor.isNativePlatform()) {
    await shareOnDevice(res.data, filename);
    return;
  }
  const url = URL.createObjectURL(res.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

export default api;
