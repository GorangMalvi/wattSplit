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
    return Promise.reject(new Error(message));
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

// Calculated split + balances for a month
export const getCalculate = (month) =>
  api.get(`/calculate/${month}`).then((res) => res.data);

// Running balances across all months
export const getHistory = () => api.get('/history').then((res) => res.data);

// Readings
export const updateReading = (month, roommateId, currentReading) =>
  api
    .put(`/readings/${month}/${roommateId}`, { current_reading: currentReading })
    .then((res) => res.data);

// Recharges
export const getRecharges = (month) =>
  api.get('/recharges', { params: { month } }).then((res) => res.data);

export const createRecharge = (payload) =>
  api.post('/recharges', payload).then((res) => res.data);

export const updateRecharge = (id, payload) =>
  api.put(`/recharges/${id}`, payload).then((res) => res.data);

export const deleteRecharge = (id) =>
  api.delete(`/recharges/${id}`).then((res) => res.data);

// Export: fetched with auth headers, then saved via a temporary link.
export const downloadExport = async (month) => {
  const res = await api.get(`/export/${month}`, { responseType: 'blob' });
  const url = URL.createObjectURL(res.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${month}_report.xlsx`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

export default api;
