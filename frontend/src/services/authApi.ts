// Authentication API boundary.
// Login and registration requests belong here so tool pages stay independent of auth details.

export { getCurrentUser, login, register, removeToken, saveToken } from './api';
