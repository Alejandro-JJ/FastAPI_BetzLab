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

// Authentication requests and token handling.

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

// File upload requests.

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

// Tool registry: drives the dashboard cards and each tool's parameter form.
export const getTools = async () => {
  const response = await api.get('/tools');
  return response.data;
};

// Image processing requests and job status polling.

// Queue a job for a given tool. The scheduler dispatches a worker container
// for it; this call only creates the job record.
export const runTool = async (toolId: string, fileId: number, params: Record<string, number>) => {
  const response = await api.post(`/tools/${toolId}/run`, {
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

// Download the processed image and metadata as one ZIP archive.
export const downloadJobResult = async (jobId: string) => {
  const response = await api.get(`/job/${jobId}/download`, {
    responseType: 'blob',
  });
  return response.data;
};

// Fetch one TIFF slice as a PNG for display in the browser.
export const getSourceSlice = async (fileId: number, sliceIndex: number) => {
  const response = await api.get(`/files/${fileId}/slice/${sliceIndex}`, { responseType: 'blob' });
  return response.data;
};

export const getResultSlice = async (jobId: string, sliceIndex: number) => {
  const response = await api.get(`/job/${jobId}/slice/${sliceIndex}`, { responseType: 'blob' });
  return response.data;
};

// Small helpers for storing and checking the access token.

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
