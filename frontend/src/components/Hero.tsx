import React, { useEffect, useState } from 'react';
import { checkBackendHealth, verifyClaimApi } from '../services/api';
import type { VerificationResultResponse } from '../types';
import { VerificationResultPanel } from './VerificationResultPanel';

interface HeroProps {
  inputRef?: React.RefObject<HTMLTextAreaElement | null>;
}

const SAMPLE_CLAIMS = [
  'Global surface temperatures have increased by 1.1°C compared to 1850–1900 averages.',
  'Electric vehicles produce zero lifetime carbon emissions across their entire lifecycle.',
  'The Great Wall of China is visible to the unaided human eye from low Earth orbit.',
  'Human brain cells cannot regenerate or create new neural connections after adulthood.',
];

export const Hero = ({ inputRef }: HeroProps) => {
  const [claim, setClaim] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [backendStatus, setBackendStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking');
  const [verificationResult, setVerificationResult] = useState<VerificationResultResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [validationWarning, setValidationWarning] = useState<string | null>(null);

  // Check backend health on mount
  useEffect(() => {
    let isMounted = true;

    async function verifyHealth() {
      try {
        await checkBackendHealth();
        if (isMounted) {
          setBackendStatus('connected');
        }
      } catch {
        if (isMounted) {
          setBackendStatus('disconnected');
        }
      }
    }

    verifyHealth();

    return () => {
      isMounted = false;
    };
  }, []);

  const handleClaimChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    // Enforce 1,000 character maximum limit
    const value = e.target.value.slice(0, 1000);
    setClaim(value);

    // Reset validation warning on new user input
    if (validationWarning) {
      setValidationWarning(null);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = claim.trim();

    // Validation for empty or whitespace-only submissions
    if (!trimmed) {
      setValidationWarning('Claim cannot contain only whitespace. Please enter a valid statement to verify.');
      return;
    }

    setValidationWarning(null);
    setErrorMessage(null);
    setIsSubmitting(true);

    try {
      const response = await verifyClaimApi(trimmed);
      setVerificationResult(response);
      setBackendStatus('connected');
    } catch (error: unknown) {
      const errorMsg =
        error instanceof Error
          ? error.message
          : 'Unable to connect to the VERITAS backend. Please ensure the server is running on port 8000.';
      setErrorMessage(errorMsg);
      if (errorMsg.includes('Cannot connect') || errorMsg.includes('Network error')) {
        setBackendStatus('disconnected');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      if (claim.trim().length > 0 && !isSubmitting) {
        handleVerify(e);
      }
    }
  };

  const handleSampleClick = (sample: string) => {
    // Populate textarea with sample claim statement
    setClaim(sample.slice(0, 1000));
    setValidationWarning(null);
    setErrorMessage(null);
    if (inputRef?.current) {
      inputRef.current.focus();
    }
  };

  const handleClear = () => {
    setClaim('');
    setVerificationResult(null);
    setErrorMessage(null);
    setValidationWarning(null);
    if (inputRef?.current) {
      inputRef.current.focus();
    }
  };

  // Button is disabled when input is empty or request is actively processing
  const isInputEmpty = claim.length === 0;

  return (
    <section id="home" className="hero-section">
      <div className="hero-content">
        {/* Tagline pill */}
        <div className="tagline-pill">
          <span className="pulse-indicator" aria-hidden="true" />
          <span className="tagline-text">Truth deserves verification.</span>
          <span className="tagline-version">v1.0 Preview</span>
        </div>

        {/* Hero Heading */}
        <h1 className="hero-heading">
          Question Everything. <br />
          <span className="hero-heading-gradient">Verify with Intelligence.</span>
        </h1>

        {/* Hero Subtitle */}
        <p className="hero-subheading">
          VERITAS empowers researchers, journalists, and everyday citizens with
          transparent AI claim verification. Utilizing cross-lingual transformer
          ensembles and authoritative evidence retrieval to substantiate the truth.
        </p>

        {/* Claim Verification Card */}
        <div className="claim-card" id="verify">
          <div className="claim-card-header">
            <div className="claim-card-title">
              <svg
                className="claim-icon"
                viewBox="0 0 20 20"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M10 2L17 5V10C17 14.14 14.02 17.91 10 18.75C5.98 17.91 3 14.14 3 10V5L10 2Z"
                  stroke="#267C78"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <circle cx="10" cy="10" r="2" fill="#267C78" />
              </svg>
              <span>Automated Claim Evaluation</span>
            </div>
            <div className="claim-card-meta">
              <span className="meta-tag">Multilingual: 100+ Languages</span>
              <span className="meta-tag health-tag" title="Backend API status at http://localhost:8000/health">
                <span className={`health-dot dot-${backendStatus}`} />
                {backendStatus === 'connected' && 'API: Online'}
                {backendStatus === 'disconnected' && 'API: Offline (port 8000)'}
                {backendStatus === 'checking' && 'API: Checking...'}
              </span>
            </div>
          </div>

          <form onSubmit={handleVerify} className="claim-form">
            <div className="textarea-wrapper">
              <textarea
                ref={inputRef}
                value={claim}
                onChange={handleClaimChange}
                onKeyDown={handleKeyDown}
                placeholder="Paste a claim you want to verify..."
                className="claim-textarea"
                rows={4}
                maxLength={1000}
                disabled={isSubmitting}
                aria-label="Paste a claim you want to verify"
              />
              <div className="textarea-footer">
                <span className="char-counter">{claim.length} / 1,000 characters</span>
                {claim.length > 0 && !isSubmitting && (
                  <button
                    type="button"
                    onClick={handleClear}
                    className="btn-clear"
                    title="Clear claim"
                  >
                    Clear text
                  </button>
                )}
              </div>
            </div>

            {/* Validation Warning Alert */}
            {validationWarning && (
              <div className="claim-status-alert alert-warning" role="alert">
                <div className="alert-icon-container">
                  <svg viewBox="0 0 20 20" fill="currentColor" className="status-icon">
                    <path
                      fillRule="evenodd"
                      d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                      clipRule="evenodd"
                    />
                  </svg>
                </div>
                <div className="alert-text">{validationWarning}</div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="claim-actions">
              <div className="pipeline-notice">
                <span className="indicator-dot" />
                <span>Neural Pipeline: XLM-RoBERTa + RoBERTa Configured</span>
              </div>

              <button
                type="submit"
                className="btn btn-primary btn-verify"
                disabled={isInputEmpty || isSubmitting}
                aria-disabled={isInputEmpty || isSubmitting}
              >
                {isSubmitting ? (
                  <>
                    <span className="btn-spinner" aria-hidden="true" />
                    <span>Verifying Claim...</span>
                  </>
                ) : (
                  <>
                    <svg
                      className="btn-icon"
                      viewBox="0 0 20 20"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path
                        d="M16.6667 9.16667V10C16.6656 11.4393 16.2023 12.8402 15.3444 13.9961C14.4866 15.1521 13.2796 16.0022 11.9022 16.4216C10.5248 16.8409 9.04948 16.8078 7.69176 16.3271C6.33405 15.8464 5.16524 14.9431 4.35759 13.7504C3.54994 12.5578 3.14674 11.1378 3.20815 9.70014C3.26956 8.26251 3.79237 6.88373 4.69894 5.76686C5.60551 4.64998 6.84814 3.85409 8.24355 3.49757C9.63897 3.14104 11.1121 3.24278 12.4417 3.7875"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                      <path
                        d="M16.6667 4.16667L10 10.8417L7.5 8.34167"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                    <span>Verify Claim</span>
                  </>
                )}
              </button>
            </div>
          </form>

          {/* Sample Prompts */}
          <div className="sample-claims-container">
            <span className="sample-label">Try with sample statements:</span>
            <div className="sample-chips">
              {SAMPLE_CLAIMS.map((sample, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="sample-chip"
                  onClick={() => handleSampleClick(sample)}
                  title="Click to populate claim"
                  disabled={isSubmitting}
                >
                  <span className="sample-quote">“</span>
                  <span className="sample-text">{sample}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Enhanced Professional Verification Result Panel */}
          <VerificationResultPanel
            result={verificationResult}
            isLoading={isSubmitting}
            error={errorMessage}
            onDismiss={() => {
              setVerificationResult(null);
              setErrorMessage(null);
            }}
          />
        </div>

        {/* Quick Highlights Bar */}
        <div className="hero-metrics">
          <div className="metric-item">
            <span className="metric-value">100+</span>
            <span className="metric-label">Supported Languages</span>
          </div>
          <div className="metric-divider" />
          <div className="metric-item">
            <span className="metric-value">Triple</span>
            <span className="metric-label">Neural Model Architecture</span>
          </div>
          <div className="metric-divider" />
          <div className="metric-item">
            <span className="metric-value">5 Distinct</span>
            <span className="metric-label">Standardized Verdicts</span>
          </div>
          <div className="metric-divider" />
          <div className="metric-item">
            <span className="metric-value">100%</span>
            <span className="metric-label">Transparent Evidence Trail</span>
          </div>
        </div>
      </div>
    </section>
  );
};
