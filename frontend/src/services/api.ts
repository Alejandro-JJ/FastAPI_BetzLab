// Frontend API client.
// This module centralizes all requests sent from the browser app to the FastAPI
// backend. It handles authentication headers, token persistence, and the upload/job
// polling endpoints used by the UI.

import axios from 'axios';

// Read the backend URL from the Vite environment so the frontend can run on a
// different host or container without changing code.
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Create an axios instance with default config
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to all requests automatically
api.interceptors.request.use(
  (config) => {
    // Get token from localStorage
    const token = localStorage.getItem('access_token');
    if (token) {
      // Add token to Authorization header
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// ==================== AUTHENTICATION ====================

// Register a new user
export const register = async (email: string, password: string) => {
  const response = await api.post('/auth/register', {
    email,
    password,
  });
  return response.data;
};

/* // Login and get access token
export const login = async (email: string, password: string) => {
  const response = await api.post('/auth/login', {
    username: email,
    password,
  });
  return response.data;
}; */
export const login = async (email: string, password: string) => {
  // Create form data (not JSON)
  const formData = new URLSearchParams();
  formData.append('username', email);
  formData.append('password', password);
  
  const response = await api.post('/auth/login', formData, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  });
  return response.data;
};

// Get current user info
export const getCurrentUser = async () => {
  const response = await api.get('/auth/me');
  return response.data;
};

// ==================== FILE UPLOAD ====================

// Upload a file
export const uploadFile = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await api.post('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

// ==================== SEGMENTATION ====================

// Run segmentation with custom parameters
export const runSegmentation = async (fileId: number, params: Record<string, number>) => {
  const response = await api.post('/run', {
    file_id: fileId,
    params,
  });
  return response.data;
};

// Get job status
export const getJobStatus = async (jobId: string) => {
  const response = await api.get(`/job/${jobId}`);
  return response.data;
};

// ==================== UTILITY ====================

// Store token in localStorage
export const saveToken = (token: string) => {
  localStorage.setItem('access_token', token);
};

// Remove token from localStorage
export const removeToken = () => {
  localStorage.removeItem('access_token');
};

// Check if user is logged in
export const isLoggedIn = () => {
  return localStorage.getItem('access_token') !== null;
};
