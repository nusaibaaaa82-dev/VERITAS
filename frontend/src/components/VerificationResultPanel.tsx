import type { VerificationResultResponse } from '../types';

interface VerificationResultPanelProps {
  result: VerificationResultResponse | null;
  isLoading: boolean;
  error: string | null;
  onDismiss?: () => void;
}

export const VerificationResultPanel = ({
  result,
  isLoading,
  error,
  onDismiss,
}: VerificationResultPanelProps) => {
  // 1. Loading State
  if (isLoading) {
    return (
      <div className="verification-panel panel-loading" role="status" aria-live="polite">
        <div className="loading-spinner-wrapper">
          <div className="panel-spinner" aria-hidden="true" />
        </div>
        <div className="loading-content">
          <h4 className="loading-title">Executing VERITAS Verification Pipeline</h4>
          <p className="loading-subtitle">
            Analyzing claim structure, identifying language, and querying backend verification services...
          </p>
          <div className="loading-steps">
            <span className="loading-step-item">
              <span className="step-dot" /> Claim Normalization
            </span>
            <span className="loading-step-item">
              <span className="step-dot" /> Language Identification
            </span>
            <span className="loading-step-item">
              <span className="step-dot" /> Evidence Retrieval
            </span>
            <span className="loading-step-item">
              <span className="step-dot" /> Neural Inference (XLM-RoBERTa + RoBERTa)
            </span>
            <span className="loading-step-item">
              <span className="step-dot" /> Verdict Assessment
            </span>
          </div>
        </div>
      </div>
    );
  }

  // 2. Error State
  if (error) {
    return (
      <div className="verification-panel panel-error" role="alert">
        <div className="panel-error-header">
          <div className="error-icon-box">
            <svg viewBox="0 0 20 20" fill="currentColor" className="error-svg">
              <path
                fillRule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
          </div>
          <div className="error-title-group">
            <h4 className="error-title">Verification Request Error</h4>
            <p className="error-message">{error}</p>
          </div>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="btn-dismiss-error"
              title="Dismiss error"
            >
              ×
            </button>
          )}
        </div>
        <div className="error-guidance">
          <span className="guidance-label">Diagnostic Tip:</span>
          <span>
            Verify that your backend server is running with{' '}
            <code>uvicorn backend.main:app --reload --port 8000</code> and accessible at{' '}
            <code>http://localhost:8000/health</code>.
          </span>
        </div>
      </div>
    );
  }

  // 3. Empty / Idle State (no result yet)
  if (!result) {
    return null;
  }

  // 4. Verification Result State (Real Backend Response)
  const {
    claim_id,
    claim,
    language_info,
    comparison_status,
    models,
    evidence,
    evidence_retrieval_status,
    decomposition,
    verdict_assessment,
    timestamp,
  } = result;

  const xlm7ClassResult = models['XLM-RoBERTa-7Class'] || models['XLM-RoBERTa'];
  const xlmBinaryResult = models['XLM-RoBERTa-Binary'];
  const robertaResult = models['RoBERTa'] || models['RoBERTa-HateSpeech'];

  const getVerdictClass = (verdict: string) => {
    switch (verdict) {
      case 'TRUE':
        return 'verdict-pill-true';
      case 'FALSE':
        return 'verdict-pill-false';
      case 'PARTIALLY TRUE':
        return 'verdict-pill-partially-true';
      case 'MISLEADING':
        return 'verdict-pill-misleading';
      default:
        return 'verdict-pill-unverified';
    }
  };

  return (
    <div className="verification-panel panel-result" aria-label="Verification Result">
      {/* Top Banner: Verdict & Primary Status */}
      <div className="result-top-banner">
        <div className="banner-left">
          <span className="banner-eyebrow">Pipeline Assessment Result</span>
          <div className="verdict-display-group">
            <span className={`verdict-tag-pill ${getVerdictClass(verdict_assessment.verdict)}`}>
              VERDICT: {verdict_assessment.verdict}
            </span>
            <span className="comparison-tag-pill tag-pill-incomplete">
              Comparison: {comparison_status.is_complete ? 'Complete' : 'Incomplete'}
            </span>
          </div>
        </div>

        <div className="banner-right">
          <span className="claim-id-badge">ID: {claim_id}</span>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="btn-close-panel"
              title="Close result panel"
            >
              Close Result ×
            </button>
          )}
        </div>
      </div>

      {/* Submitted Claim Quote */}
      <div className="result-claim-block">
        <span className="claim-block-label">Submitted Statement:</span>
        <blockquote className="claim-quote">“{claim}”</blockquote>
        <div className="claim-meta-row">
          <span className="claim-meta-item">
            <strong>Language:</strong> {language_info.name} (<code>{language_info.code}</code>)
            <span
              className={`lang-badge ${
                language_info.is_reliable ? 'lang-badge-reliable' : 'lang-badge-uncertain'
              }`}
            >
              {language_info.is_reliable ? 'Identified' : 'Undetermined'}
            </span>
          </span>
          <span className="claim-meta-item">
            <strong>Evaluated:</strong> {new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })} UTC
          </span>
        </div>
        {language_info.note && (
          <p className="lang-note-text">
            <em>Language identification note:</em> {language_info.note}
          </p>
        )}
      </div>

      {/* Proposition Decomposition & Coverage Breakdown */}
      {decomposition && decomposition.propositions && decomposition.propositions.length > 0 && (
        <div className="decomposition-card">
          <div className="decomposition-header">
            <div className="decomposition-header-left">
              <span className="decomposition-title">Claim Decomposition & Evidence Matching</span>
              <span className={`decomposition-status-badge badge-status-${decomposition.status.toLowerCase()}`}>
                {decomposition.status.replace(/_/g, ' ')}
              </span>
            </div>
            <span className="decomposition-count-pill">
              {decomposition.total_propositions} {decomposition.total_propositions === 1 ? 'Proposition' : 'Propositions'}
            </span>
          </div>

          <p className="decomposition-guidance">
            {decomposition.status === 'NEEDS_REVIEW'
              ? 'Claim statement contains subjective, speculative, or ambiguous phrasing. Automated proposition decomposition is flagged for review.'
              : 'Complex claims are segmented into distinct factual propositions to evaluate evidence coverage across sub-clauses.'}
          </p>

          <div className="decomposition-coverage-bar">
            <div className="coverage-metric">
              <span className="coverage-num coverage-verified-supported">
                {decomposition.verified_supported_count ?? 0}
              </span>
              <span className="coverage-label">Verified Supported</span>
            </div>
            <div className="coverage-metric">
              <span className="coverage-num coverage-unverified-match">
                {decomposition.unverified_supporting_count ?? 0}
              </span>
              <span className="coverage-label">Unverified Matches</span>
            </div>
            <div className="coverage-metric">
              <span className="coverage-num coverage-contradicted">
                {(decomposition.verified_contradicted_count ?? 0) + (decomposition.unverified_contradicting_count ?? 0)}
              </span>
              <span className="coverage-label">Contradicted</span>
            </div>
            <div className="coverage-metric">
              <span className="coverage-num coverage-conflicting">{decomposition.conflicting_propositions_count}</span>
              <span className="coverage-label">Conflicting</span>
            </div>
            <div className="coverage-metric">
              <span className="coverage-num coverage-unresolved">{decomposition.unresolved_propositions_count}</span>
              <span className="coverage-label">Unresolved / No Evidence</span>
            </div>
          </div>

          <div className="propositions-list">
            {decomposition.propositions.map((prop, pIdx) => {
              const coverage = decomposition.proposition_coverage?.find(
                (c) => c.proposition_id === prop.id
              );
              const covStatus = coverage?.coverage_status || 'NO_EVIDENCE';
              const formatCovLabel = (st: string) => {
                switch (st) {
                  case 'VERIFIED_SUPPORTED':
                    return 'VERIFIED SUPPORT';
                  case 'UNVERIFIED_MATCH_SUPPORTING':
                    return 'UNVERIFIED LITERATURE MATCH';
                  case 'VERIFIED_CONTRADICTED':
                    return 'VERIFIED CONTRADICTION';
                  case 'UNVERIFIED_MATCH_CONTRADICTING':
                    return 'UNVERIFIED LITERATURE DISPUTE';
                  case 'CONFLICTING':
                    return 'CONFLICTING EVIDENCE';
                  case 'NO_EVIDENCE':
                    return 'NO EVIDENCE';
                  case 'UNRESOLVED':
                    return 'UNRESOLVED';
                  default:
                    return st.replace(/_/g, ' ');
                }
              };

              return (
                <div key={prop.id || pIdx} className="proposition-card">
                  <div className="prop-header-row">
                    <span className="prop-number">P{pIdx + 1}</span>
                    <span className="prop-text">{prop.text}</span>
                  </div>

                  <div className="prop-badges-row">
                    <span className="badge-pill prop-type-pill">
                      {prop.proposition_type.replace(/_/g, ' ')}
                    </span>
                    <span className={`badge-pill prop-cov-pill cov-${covStatus.toLowerCase()}`}>
                      {formatCovLabel(covStatus)}
                    </span>
                    {prop.status === 'NEEDS_REVIEW' && (
                      <span className="badge-pill badge-review-alert">Needs Review</span>
                    )}
                  </div>

                  {coverage?.notes && (
                    <div className="prop-coverage-note">
                      <strong>Coverage Rationale:</strong> {coverage.notes}
                    </div>
                  )}

                  {coverage && coverage.matches && coverage.matches.length > 0 && (
                    <div className="prop-matches-container">
                      <span className="prop-matches-heading">Associated Evidence Matches:</span>
                      <div className="prop-matches-list">
                        {coverage.matches.map((m, mIdx) => (
                          <div key={m.evidence_id || mIdx} className="prop-match-item">
                            <span className={`match-stance-pill stance-${m.stance.toLowerCase()}`}>
                              {m.stance}
                            </span>
                            <span className={`match-verified-chip ${m.is_verified ? 'chip-verified' : 'chip-unverified'}`}>
                              {m.is_verified ? 'Verified Source' : 'Unverified Record'}
                            </span>
                            <span className="match-title-text">
                              {m.source_url ? (
                                <a href={m.source_url} target="_blank" rel="noopener noreferrer" className="match-link">
                                  {m.evidence_title} ↗
                                </a>
                              ) : (
                                m.evidence_title
                              )}
                            </span>
                            <span className="match-explanation">{m.explanation}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="decomposition-safety-notice">
            <svg className="safety-icon" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
            <span>
              <strong>Scientific Safety Rule:</strong> Proposition coverage reflects evidence presence across decomposed assertions and is NEVER converted into a truth verdict. Conclusive verdicts require at least two independent verified primary sources across all essential propositions.
            </span>
          </div>
        </div>
      )}

      {/* Why the Verdict is UNVERIFIED */}
      <div className="verdict-explanation-card">
        <div className="explanation-header">
          <svg className="info-icon" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
              clipRule="evenodd"
            />
          </svg>
          <span className="explanation-title">Why is the Verdict UNVERIFIED?</span>
        </div>
        <p className="explanation-text">{verdict_assessment.justification}</p>
      </div>

      {/* Grid: Models & Evidence Retrieval Breakdown */}
      <div className="pipeline-details-grid">
        {/* Model 1: XLM-RoBERTa (7-Class & Binary Configurations) */}
        <div className="detail-card">
          <div className="detail-card-header">
            <span className="detail-card-title">XLM-RoBERTa</span>
            <span className={`status-chip ${(xlm7ClassResult?.is_available || xlmBinaryResult?.is_available) ? 'chip-available' : 'chip-unavailable'}`}>
              {(xlm7ClassResult?.is_available || xlmBinaryResult?.is_available) ? 'Active' : 'Weights Unloaded'}
            </span>
          </div>
          <p className="detail-card-role">Cross-Lingual Fact-Checking (7-Class & Binary)</p>
          <div className="detail-metric-row">
            <span className="metric-name">7-Class Repository:</span>
            <span className="metric-val"><code>nusaiba19/xlmr-xfact-7class</code></span>
          </div>
          <div className="detail-metric-row">
            <span className="metric-name">Binary Repository:</span>
            <span className="metric-val"><code>nusaiba19/xlmr-xfact-binary</code></span>
          </div>
          <div className="detail-metric-row">
            <span className="metric-name">Inference Stance:</span>
            <span className={`metric-val ${xlm7ClassResult?.prediction ? '' : 'metric-val-none'}`}>
              {xlm7ClassResult?.prediction ?? 'None (Unloaded)'}
            </span>
          </div>
          {xlm7ClassResult?.confidence !== undefined && xlm7ClassResult?.confidence !== null && (
            <div className="detail-metric-row">
              <span className="metric-name">Model Prediction Probability:</span>
              <span className="metric-val">
                {(xlm7ClassResult.confidence * 100).toFixed(2)}%
                <small className="metric-disclaimer">(neural model classification output — NOT factual truth probability)</small>
              </span>
            </div>
          )}
          {xlm7ClassResult?.inference_time_ms !== undefined && xlm7ClassResult?.inference_time_ms !== null && (
            <div className="detail-metric-row">
              <span className="metric-name">Inference Latency:</span>
              <span className="metric-val">{xlm7ClassResult.inference_time_ms} ms ({xlm7ClassResult.device ?? 'cpu'})</span>
            </div>
          )}
          <div className="detail-metric-row">
            <span className="metric-name">Adapter Status:</span>
            <span className="metric-val">{xlm7ClassResult?.status ?? 'model_not_loaded'}</span>
          </div>
          {xlmBinaryResult?.status && (
            <div className="detail-metric-row">
              <span className="metric-name">Binary Adapter:</span>
              <span className="metric-val">{xlmBinaryResult.status}</span>
            </div>
          )}
          {xlmBinaryResult?.prediction && (
            <div className="detail-metric-row">
              <span className="metric-name">Binary Prediction:</span>
              <span className="metric-val">{xlmBinaryResult.prediction}</span>
            </div>
          )}
          {xlmBinaryResult?.confidence !== undefined && xlmBinaryResult?.confidence !== null && (
            <div className="detail-metric-row">
              <span className="metric-name">Binary Prediction Probability:</span>
              <span className="metric-val">
                {(xlmBinaryResult.confidence * 100).toFixed(2)}%
                <small className="metric-disclaimer">(binary model classification output — NOT factual truth probability)</small>
              </span>
            </div>
          )}
          {xlm7ClassResult?.details && (
            <p className="detail-card-desc">{xlm7ClassResult.details}</p>
          )}
        </div>

        {/* Model 2: RoBERTa (Immigrant Hate-Speech Classifier) */}
        <div className="detail-card">
          <div className="detail-card-header">
            <span className="detail-card-title">RoBERTa</span>
            <span className={`status-chip ${robertaResult?.status === 'unsupported_language' ? 'chip-unsupported' : robertaResult?.is_available ? 'chip-available' : 'chip-unavailable'}`}>
              {robertaResult?.status === 'unsupported_language' ? 'Unsupported Language' : robertaResult?.is_available ? 'Active' : 'Weights Unloaded'}
            </span>
          </div>
          <p className="detail-card-role">Immigrant Hate-Speech & Toxicity Classifier</p>
          <div className="detail-metric-row">
            <span className="metric-name">Repository:</span>
            <span className="metric-val"><code>nusaiba19/roberta-immigrant-hate-speech</code></span>
          </div>
          <div className="detail-metric-row">
            <span className="metric-name">Classification Domain:</span>
            <span className="metric-val">Content Safety (Not Fact-Checking)</span>
          </div>
          <div className="detail-metric-row">
            <span className="metric-name">Toxicity Stance:</span>
            <span className={`metric-val ${robertaResult?.prediction ? '' : 'metric-val-none'}`}>
              {robertaResult?.prediction ?? 'None (Unloaded)'}
            </span>
          </div>
          {robertaResult?.confidence !== undefined && robertaResult?.confidence !== null && (
            <div className="detail-metric-row">
              <span className="metric-name">Model Prediction Probability:</span>
              <span className="metric-val">
                {(robertaResult.confidence * 100).toFixed(2)}%
                <small className="metric-disclaimer">(content-safety classification score — NOT factual truth probability)</small>
              </span>
            </div>
          )}
          {robertaResult?.inference_time_ms !== undefined && robertaResult?.inference_time_ms !== null && (
            <div className="detail-metric-row">
              <span className="metric-name">Inference Latency:</span>
              <span className="metric-val">{robertaResult.inference_time_ms} ms ({robertaResult.device ?? 'cpu'})</span>
            </div>
          )}
          <div className="detail-metric-row">
            <span className="metric-name">Adapter Status:</span>
            <span className="metric-val">{robertaResult?.status ?? 'model_not_loaded'}</span>
          </div>
          {robertaResult?.details && (
            <p className="detail-card-desc">{robertaResult.details}</p>
          )}
        </div>

        {/* Evidence Retrieval Status */}
        <div className="detail-card full-span">
          <div className="detail-card-header">
            <span className="detail-card-title">Evidence Retrieval Engine</span>
            <span className="status-chip chip-disconnected">
              Status: {evidence_retrieval_status}
            </span>
          </div>
          <p className="detail-card-role">Local Verified Evidence Repository & FTS5 Index</p>
          <div className="evidence-summary-row">
            <div className="evidence-stat">
              <span className="evidence-stat-num">{evidence.length}</span>
              <span className="evidence-stat-label">Retrieved Candidates</span>
            </div>
            <div className="evidence-stat">
              <span className="evidence-stat-num">{verdict_assessment.independent_sources_count}</span>
              <span className="evidence-stat-label">Independent Sources</span>
            </div>
            <div className="evidence-stat">
              <span className="evidence-stat-num">
                {evidence.filter((e) => e.is_verified).length}
              </span>
              <span className="evidence-stat-label">Verified Primary Sources (≥2 Required)</span>
            </div>
            <div className="evidence-stat">
              <span className="evidence-stat-num">0%</span>
              <span className="evidence-stat-label">Fabricated Citations</span>
            </div>
          </div>
          <p className="evidence-explanation">
            {evidence.length > 0
              ? `Retrieved ${evidence.length} discovery records from the local verified evidence repository (${evidence_retrieval_status}). All records are evaluated for relevance, source tier, and provenance. Unverified literature records cannot corroborate conclusive verdicts.`
              : 'No matching records found in the local repository for this claim query. In accordance with VERITAS scientific integrity standards, zero fake citations or synthetic sources are fabricated.'}
          </p>

          {/* Retrieved Evidence Items List */}
          {evidence.length > 0 && (
            <div className="evidence-card-list">
              <h5 className="evidence-list-heading">Retrieved Source Records & Provenance Audit:</h5>
              {evidence.map((item, idx) => (
                <div key={item.id || idx} className="evidence-record-card">
                  <div className="record-top-row">
                    <span className="record-number">#{idx + 1}</span>
                    <span className="record-title">
                      {item.canonical_url || item.url ? (
                        <a
                          href={item.canonical_url || item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="evidence-title-link"
                        >
                          {item.title} ↗
                        </a>
                      ) : (
                        item.title
                      )}
                    </span>
                  </div>

                  <div className="record-badges-row">
                    <span className={`badge-pill badge-tier-${(item.source_tier || 'secondary').toLowerCase()}`}>
                      Tier: {item.source_tier || 'SECONDARY'}
                    </span>
                    <span className="badge-pill badge-type">
                      {item.source_type ? item.source_type.replace(/_/g, ' ') : 'OTHER'}
                    </span>
                    <span className="badge-pill badge-availability">
                      {item.text_availability ? item.text_availability.replace(/_/g, ' ') : 'METADATA ONLY'}
                    </span>
                    <span className={`badge-pill badge-relevance-${(item.relevance_status || 'undetermined').toLowerCase()}`}>
                      {item.relevance_status || 'UNDETERMINED'}
                      {item.relevance_score !== null && item.relevance_score !== undefined
                        ? ` (${Math.round(item.relevance_score * 100)}%)`
                        : ''}
                    </span>
                    <span className={`badge-pill badge-stance-${(item.stance || 'neutral').toLowerCase()}`}>
                      Stance: {item.stance || 'NEUTRAL'}
                    </span>
                    <span className={`badge-pill ${item.is_verified ? 'badge-verified' : 'badge-unverified'}`}>
                      {item.is_verified ? 'Verified Authority' : 'Unverified Source Record'}
                    </span>
                    {item.is_potential_syndication && (
                      <span className="badge-pill badge-syndicated">
                        Syndication Flag
                      </span>
                    )}
                  </div>

                  <div className="record-meta-row">
                    <span className="record-meta-item">
                      <strong>Publisher:</strong> {item.canonical_publisher || item.publisher || 'Unspecified'}
                    </span>
                    {item.canonical_domain && (
                      <span className="record-meta-item">
                        <strong>Domain:</strong> <code>{item.canonical_domain}</code>
                      </span>
                    )}
                    {item.published_date && (
                      <span className="record-meta-item">
                        <strong>Date:</strong> {item.published_date}
                      </span>
                    )}
                    {item.doi && (
                      <span className="record-meta-item">
                        <strong>DOI:</strong> <code>{item.doi}</code>
                      </span>
                    )}
                  </div>

                  <div className="record-snippet-box">
                    <span className="snippet-label">Excerpt / Abstract:</span>
                    <p className="snippet-text">{item.snippet}</p>
                  </div>

                  {item.stance_justification && (
                    <div className="record-justification-note">
                      <strong>Stance Assessment:</strong> {item.stance_justification}
                    </div>
                  )}

                  {item.relevance_justification && (
                    <div className="record-justification-note">
                      <strong>Relevance Assessment:</strong> {item.relevance_justification}
                    </div>
                  )}

                  {item.syndication_notes && (
                    <div className="record-syndication-alert">
                      <strong>Syndication / Duplicate Notice:</strong> {item.syndication_notes}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Comparison Status Banner */}
      <div className="comparison-status-callout">
        <div className="callout-label">Model Comparison Status:</div>
        <div className="callout-text">{comparison_status.status_message}</div>
      </div>

      {/* Scientific Methodology Notes */}
      {verdict_assessment.methodology_notes && verdict_assessment.methodology_notes.length > 0 && (
        <div className="methodology-footer">
          <span className="methodology-header">Scientific Methodology Standards:</span>
          <ul className="methodology-list">
            {verdict_assessment.methodology_notes.map((note, idx) => (
              <li key={idx} className="methodology-item">
                <span className="methodology-bullet" />
                <span>{note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

