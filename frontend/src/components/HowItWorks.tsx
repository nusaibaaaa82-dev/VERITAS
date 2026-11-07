import type { PipelineStep } from '../types';

const STEPS: PipelineStep[] = [
  {
    step: '01',
    title: 'Claim Parsing & Entity Disambiguation',
    description:
      'The raw claim is analyzed by the claim decomposition engine to isolate core factual propositions, quantitative assertions, temporal baselines, and causal sub-clauses.',
    detail: 'Supports 100+ native languages without translation degradation.',
  },
  {
    step: '02',
    title: 'Hybrid Evidence Retrieval',
    description:
      'The retrieval pipeline conducts FTS5 BM25 queries across local verified records and queries domain-prioritized public repositories (PubMed, WHO, NASA, USGS, World Bank, OpenAlex, Crossref).',
    detail: 'Indexes millions of peer-reviewed articles and primary records.',
  },
  {
    step: '03',
    title: 'Neural Stance & Safety Evaluation',
    description:
      'XLM-RoBERTa evaluates the claim across 7-class and binary veracity benchmarks, while RoBERTa independently screens for immigrant hate speech and dehumanizing rhetoric.',
    detail: 'Preserves both granular and binary classification configurations.',
  },
  {
    step: '04',
    title: 'Verdict Calibration & Attribution',
    description:
      'A calibration layer maps the aggregated evidence weights into one of the 5 standardized verdicts, generating transparent source links and justification rationale.',
    detail: 'Zero hallucinated verdicts; completely anchored in cited evidence.',
  },
];

export const HowItWorks = () => {
  return (
    <section id="how-it-works" className="how-it-works-section">
      <div className="section-container">
        <div className="section-header">
          <span className="section-badge">Verification Lifecycle</span>
          <h2 className="section-title">How VERITAS Verifies Claims</h2>
          <p className="section-description">
            A transparent, four-phase analytical process that moves from raw claim to substantiated
            fact without human bias or synthetic hallucinations.
          </p>
        </div>

        <div className="steps-container">
          {STEPS.map((stepItem, idx) => (
            <div key={idx} className="step-card">
              <div className="step-card-header">
                <span className="step-number">{stepItem.step}</span>
                <div className="step-connector" aria-hidden="true" />
              </div>
              <h3 className="step-title">{stepItem.title}</h3>
              <p className="step-description">{stepItem.description}</p>
              <div className="step-detail-pill">
                <span className="detail-bullet" />
                <span className="detail-text">{stepItem.detail}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
