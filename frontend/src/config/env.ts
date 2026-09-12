/**
 * Environment configuration for IBVAP Frontend.
 *
 * Reads Vite environment variables with safe localhost defaults.
 */

const DEFAULT_API_BASE_URL = 'http://localhost:8000/api/v1';
const DEFAULT_WS_BASE_URL = 'ws://localhost:8000/api/v1';

export const config = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL as string) || DEFAULT_API_BASE_URL,
  wsBaseUrl: (import.meta.env.VITE_WS_BASE_URL as string) || DEFAULT_WS_BASE_URL,
  isDev: import.meta.env.DEV,
  isProd: import.meta.env.PROD,
};
