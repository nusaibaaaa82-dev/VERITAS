/**
 * VERITAS API Client Service
 *
 * Provides reusable functions to interact with the VERITAS backend.
 * Automatically adapts between local Vite development (proxying/pointing to http://localhost:8000),
 * deployed separate two-service production (pointing to https://veritas-backend-htl6.onrender.com),
 * and unified production deployments (e.g., Hugging Face Spaces same-origin relative paths).
 */

import type { HealthResponse, VerificationResultResponse } from '../types';

function getApiBaseUrl(): string {
  // 1. Explicit environment variable override (injected at build time via Vite VITE_API_BASE_URL)
  if (
    typeof import.meta !== 'undefined' &&
    import.meta.env &&
    typeof import.meta.env.VITE_API_BASE_URL === 'string' &&
    import.meta.env.VITE_API_BASE_URL.trim() !== ''
  ) {
    return import.meta.env.VITE_API_BASE_URL.trim().replace(/\/+$/, '');
  }

  // 2. Browser runtime inspection
  if (typeof window !== 'undefined' && window.location) {
    const hostname = window.location.hostname.toLowerCase();
    const port = window.location.port;

    // Local Vite development server (default ports 5173, 5174)
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      if (port === '5173' || port === '5174') {
        return 'http://localhost:8000';
      }
      // If accessed directly on local backend port, use same-origin relative URLs
      return '';
    }

    // Render production deployment: when served from veritas-frontend on Render
    if (
      hostname === 'veritas-frontend-0lhx.onrender.com' ||
      hostname.includes('veritas-frontend') ||
      hostname.endsWith('.onrender.com')
    ) {
      return 'https://veritas-backend-htl6.onrender.com';
    }
  }

  // 3. Unified production deployment default (e.g., Hugging Face Spaces or unified server same-origin)
  return '';
}

export const API_BASE_URL = getApiBaseUrl();

export class ApiError extends Error {
  statusCode?: number;
  details?: string[];

  constructor(message: string, statusCode?: number, details?: string[]) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
    this.details = details;
  }
}

/**
 * Check backend service health status using GET /health
 */
export async function checkBackendHealth(): Promise<HealthResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    });

    if (!response.ok) {
      throw new ApiError(
        `Backend health check returned status ${response.status}: ${response.statusText}`,
        response.status
      );
    }

    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      throw new ApiError(
        `Expected JSON response from health endpoint, but received '${contentType}'. Target URL: ${API_BASE_URL}/health`
      );
    }

    const data: HealthResponse = await response.json();
    return data;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    const targetUrl = `${API_BASE_URL || (typeof window !== 'undefined' ? window.location.origin : '')}/health`;
    throw new ApiError(
      `Cannot connect to the VERITAS backend service at ${targetUrl}. Please ensure the backend is running and accessible.`
    );
  }
}

/**
 * Submit claim for pipeline verification using POST /api/verify
 */
export async function verifyClaimApi(
  claim: string,
  language?: string
): Promise<VerificationResultResponse> {
  const payload: { claim: string; language?: string } = {
    claim: claim.trim(),
  };

  if (language && language.trim()) {
    payload.language = language.trim();
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/verify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      let errorMessage = `Verification failed (${response.status} ${response.statusText})`;
      let details: string[] | undefined;

      try {
        const errorJson = await response.json();
        if (errorJson.details && Array.isArray(errorJson.details)) {
          details = errorJson.details;
          errorMessage = errorJson.details.join('; ');
        } else if (errorJson.detail) {
          errorMessage = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail);
        }
      } catch {
        // Fallback to text error message if JSON parsing fails
      }

      throw new ApiError(errorMessage, response.status, details);
    }

    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      throw new ApiError(
        `Expected JSON response from verification endpoint, but received '${contentType}'. Verify API configuration.`
      );
    }

    const data: VerificationResultResponse = await response.json();
    return data;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    const targetUrl = `${API_BASE_URL || (typeof window !== 'undefined' ? window.location.origin : '')}/api/verify`;
    throw new ApiError(
      `Network error connecting to the VERITAS backend at ${targetUrl}. Please check your network connection or retry shortly.`
    );
  }
}
