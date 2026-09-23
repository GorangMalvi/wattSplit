import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.message || 'Something went wrong';
    return Promise.reject(new Error(message));
  }
);

// Months
export const getMonths = () => api.get('/months').then((res) => res.data);

export const getMonth = (month) => api.get(`/months/${month}`).then((res) => res.data);

export const createMonth = (payload) => api.post('/months', payload).then((res) => res.data);

export const updateMonth = (month, payload) =>
  api.put(`/months/${month}`, payload).then((res) => res.data);

// Roommates
export const getRoommates = () => api.get('/roommates').then((res) => res.data);

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

// Export
export const getExportUrl = (month) =>
  `${API_BASE_URL.replace(/\/$/, '')}/export/${month}`;

export default api;
