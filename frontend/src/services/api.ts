/**
 * VERITAS API Client Service
 *
 * Provides reusable functions to interact with the VERITAS backend.
 * Automatically adapts between local Vite development (proxying/pointing to http://localhost:8000)
 * and unified production deployments (e.g., Hugging Face Spaces same-origin relative paths).
 */

import type { HealthResponse, VerificationResultResponse } from '../types';

function getApiBaseUrl(): string {
  // 1. Explicit environment variable override
  if (typeof import.meta !== 'undefined' && import.meta.env && typeof import.meta.env.VITE_API_BASE_URL === 'string') {
    return import.meta.env.VITE_API_BASE_URL;
  }
  // 2. Local Vite development server fallback
  if (typeof window !== 'undefined' && window.location) {
    if (window.location.hostname === 'localhost' && (window.location.port === '5173' || window.location.port === '5174')) {
      return 'http://localhost:8000';
    }
  }
  // 3. Unified production deployment (e.g., Hugging Face Spaces same-origin)
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
        `Backend returned status ${response.status}: ${response.statusText}`,
        response.status
      );
    }

    const data: HealthResponse = await response.json();
    return data;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      'Cannot connect to the VERITAS backend service. Please check your network connection or verify that the server is running.'
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

    const data: VerificationResultResponse = await response.json();
    return data;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      'Network error connecting to the VERITAS backend. Please check your network connection or retry shortly.'
    );
  }
}
