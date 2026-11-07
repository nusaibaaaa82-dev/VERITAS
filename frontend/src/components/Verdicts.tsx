import type { VerdictItem } from '../types';

const VERDICTS_DATA: VerdictItem[] = [
  {
    id: 'verdict-true',
    name: 'TRUE',
    badge: 'Verified Truth',
    tagline: 'Factually accurate, complete, and supported by primary evidence.',
    description:
      'The statement contains no material misrepresentation, omission, or distortion. It is confirmed by established scientific consensus, official statistics, or reputable primary documentation.',
    criteria: [
      'Core claim aligns directly with authoritative records',
      'Context and scope are accurately represented',
      'No selective omission of contradictory facts',
    ],
    color: {
      primary: '#237A57',
      bg: '#EBF5F0',
      border: '#BCE3D1',
    },
  },
  {
    id: 'verdict-false',
    name: 'FALSE',
    badge: 'Demonstrably Inaccurate',
    tagline: 'Factually false or directly contradicted by reliable data.',
    description:
      'The primary premise of the claim is demonstrably inaccurate, fabricated, or thoroughly refuted by verified historical, scientific, or archival records.',
    criteria: [
      'Contradicted by verifiable empirical proof',
      'Asserts events or outcomes that did not occur',
      'Relies on fabricated quotes, altered media, or pseudo-facts',
    ],
    color: {
      primary: '#B54747',
      bg: '#FDF2F2',
      border: '#F1C3C3',
    },
  },
  {
    id: 'verdict-partially-true',
    name: 'PARTIALLY TRUE',
    badge: 'Nuanced Accuracy',
    tagline: 'Contains factual elements but lacks vital context or precision.',
    description:
      'The claim incorporates genuine facts or real statistics, but oversimplifies, conflates timelines, or leaves out essential context required for an accurate interpretation.',
    criteria: [
      'Factual foundation exists but is overstated or overgeneralized',
      'Omits crucial conditional factors or caveats',
      'Merges confirmed facts with unconfirmed speculation',
    ],
    color: {
      primary: '#A66A16',
      bg: '#FEF7EE',
      border: '#F6D8A8',
    },
  },
  {
    id: 'verdict-misleading',
    name: 'MISLEADING',
    badge: 'Distorted Context',
    tagline: 'Uses real data or quotes to guide readers to a deceptive conclusion.',
    description:
      'While individual phrases or figures may be technically authentic, the logical framing, selective cherry-picking, or emotional spin creates an intentionally erroneous impression.',
    criteria: [
      'Selective quotation stripped of explanatory surroundings',
      'Correlation falsely presented as direct causation',
      'Outdated numbers presented as representing current reality',
    ],
    color: {
      primary: '#7654A3',
      bg: '#F5F1FA',
      border: '#D8C7EB',
    },
  },
  {
    id: 'verdict-unverified',
    name: 'UNVERIFIED',
    badge: 'Inconclusive Data',
    tagline: 'Insufficient evidence or emerging situation prevents verification.',
    description:
      'Current publicly available evidence, scientific inquiry, or archival repositories are insufficient or too contradictory to render a conclusive determination at this time.',
    criteria: [
      'Primary source documentation is currently inaccessible',
      'Credible experts hold conflicting, unreconciled positions',
      'Breaking or fast-developing events with volatile reports',
    ],
    color: {
      primary: '#64748B',
      bg: '#F1F5F9',
      border: '#CBD5E1',
    },
  },
];

export const Verdicts = () => {
  return (
    <section id="verdicts" className="verdicts-section">
      <div className="section-container">
        <div className="section-header">
          <span className="section-badge">Standardized Classification</span>
          <h2 className="section-title">The Five VERITAS Verdicts</h2>
          <p className="section-description">
            Information isn&apos;t binary. VERITAS classifies claims through five rigorous,
            standardized verdicts, providing nuanced context rather than oversimplified judgments.
          </p>
        </div>

        <div className="verdicts-grid">
          {VERDICTS_DATA.map((verdict) => (
            <div
              key={verdict.id}
              className="verdict-card"
              style={{
                borderTop: `3px solid ${verdict.color.primary}`,
              }}
            >
              <div className="verdict-card-top">
                <span
                  className="verdict-badge"
                  style={{
                    backgroundColor: verdict.color.bg,
                    color: verdict.color.primary,
                    borderColor: verdict.color.border,
                  }}
                >
                  {verdict.badge}
                </span>
                <span
                  className="verdict-name"
                  style={{ color: verdict.color.primary }}
                >
                  {verdict.name}
                </span>
              </div>

              <h3 className="verdict-tagline">{verdict.tagline}</h3>
              <p className="verdict-description">{verdict.description}</p>

              <div className="verdict-criteria-box">
                <span className="criteria-header">Evaluation Criteria:</span>
                <ul className="criteria-list">
                  {verdict.criteria.map((item, idx) => (
                    <li key={idx} className="criteria-item">
                      <svg
                        className="criteria-bullet"
                        viewBox="0 0 16 16"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                        style={{ color: verdict.color.primary }}
                      >
                        <path
                          d="M6 12L10 8L6 4"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
