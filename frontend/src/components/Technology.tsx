import type { TechnologyItem } from '../types';

const TECH_COMPONENTS: TechnologyItem[] = [
  {
    name: 'XLM-RoBERTa',
    role: 'Cross-Lingual Fact-Checking (7-Class & Binary)',
    architecture: 'Transformer Encoder fine-tuned on multilingual X-Fact benchmark',
    description:
      'XLM-RoBERTa is integrated under two distinct classification configurations: a 7-class configuration (nusaiba19/xlmr-xfact-7class) for nuanced multilingual veracity and a binary configuration (nusaiba19/xlmr-xfact-binary) for direct assertion verification. It captures syntactic subtleties across 100+ languages to prevent translation bias.',
    highlights: [
      '7-class granular veracity configuration (nusaiba19/xlmr-xfact-7class)',
      'Binary assertion verification configuration (nusaiba19/xlmr-xfact-binary)',
      'Trained across 100+ native languages without translation degradation',
    ],
    tag: 'Fact-Checking Engine',
  },
  {
    name: 'RoBERTa',
    role: 'Immigrant Hate-Speech & Toxicity Detection',
    architecture: 'Robustly Optimized BERT Pretraining (Safety Classifier)',
    description:
      'Dedicated classifier fine-tuned on immigrant hate-speech corpora (nusaiba19/roberta-immigrant-hate-speech). Within VERITAS, RoBERTa inspects claims for dehumanizing language, xenophobic targeting, and toxic rhetoric against immigrant communities. Crucially, it serves as a content-safety layer and is strictly NOT a fact-checking veracity classifier.',
    highlights: [
      'Immigrant hate-speech repository (nusaiba19/roberta-immigrant-hate-speech)',
      'Identifies xenophobic stereotypes and dehumanizing framing',
      'Strictly separated from factual truth and evidence-based verdicts',
    ],
    tag: 'Safety & Toxicity Classifier',
  },
  {
    name: 'Evidence Retrieval',
    role: 'Hybrid FTS5 Lexical & Public Provider Aggregation',
    architecture: 'Dual-Stage Retrieval: SQLite FTS5 BM25 Indexing + Public Authority Provider APIs',
    description:
      'No fact-checker should rely purely on parametric memory. VERITAS pairs neural models with an intelligent retrieval pipeline that scours peer-reviewed scientific journals, government archives, authoritative databases, and international treaty repositories to extract real-world ground-truth documents.',
    highlights: [
      'SQLite FTS5 BM25 full-text indexing for local verified evidence repository',
      'Cross-lingual concept mapping for non-English scientific discovery',
      'Dynamic entity & proposition relevance filtering across 9 public repositories',
    ],
    tag: 'Ground-Truth Pipeline',
  },
];

export const Technology = () => {
  return (
    <section id="technology" className="tech-section">
      <div className="section-container">
        <div className="section-header">
          <span className="section-badge">AI Architecture</span>
          <h2 className="section-title">Powered by Cutting-Edge NLP Models</h2>
          <p className="section-description">
            VERITAS incorporates specialized neural transformers—
            <strong> XLM-RoBERTa</strong> (7-class & binary fact-checking) and <strong>RoBERTa</strong> (immigrant hate-speech safety)—alongside
            an intelligent multi-source evidence retrieval engine for transparent, verifiable truth.
          </p>
        </div>

        {/* 3 Pillars Grid */}
        <div className="tech-grid">
          {TECH_COMPONENTS.map((tech, idx) => (
            <div key={idx} className="tech-card">
              <div className="tech-card-header">
                <span className="tech-tag">{tech.tag}</span>
                <span className="tech-index">0{idx + 1}</span>
              </div>

              <h3 className="tech-title">{tech.name}</h3>
              <p className="tech-role">{tech.role}</p>

              <div className="tech-arch-pill">
                <span className="pill-dot" />
                <span className="pill-text">{tech.architecture}</span>
              </div>

              <p className="tech-description">{tech.description}</p>

              <div className="tech-highlights">
                <span className="highlights-title">Core Capabilities</span>
                <ul className="highlights-list">
                  {tech.highlights.map((item, hIdx) => (
                    <li key={hIdx} className="highlight-item">
                      <svg
                        className="highlight-check"
                        viewBox="0 0 16 16"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                      >
                        <path
                          d="M13.3334 4L6.00008 11.3333L2.66675 8"
                          stroke="#267C78"
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

        {/* Architecture Synergy Diagram Box */}
        <div className="architecture-synergy-box">
          <div className="synergy-header">
            <div className="synergy-badge">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#267C78"
                strokeWidth="2"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
              <span>Pipeline Integration</span>
            </div>
            <h3 className="synergy-title">How the Neural Models Collaborate</h3>
            <p className="synergy-desc">
              Rather than depending on a single model or black-box LLM generation, VERITAS
              separates claim comprehension from stance reasoning.
            </p>
          </div>

          <div className="flow-diagram">
            <div className="flow-step">
              <div className="step-circle">1</div>
              <div className="step-label">Input Claim</div>
              <div className="step-sub">User statement in 100+ languages</div>
            </div>

            <div className="flow-arrow">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M5 12H19M19 12L12 5M19 12L12 19" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>

            <div className="flow-step">
              <div className="step-circle">2</div>
              <div className="step-label">Evidence Retrieval</div>
              <div className="step-sub">FTS5 BM25 + Multi-source catalog search</div>
            </div>

            <div className="flow-arrow">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M5 12H19M19 12L12 5M19 12L12 19" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>

            <div className="flow-step highlight-step">
              <div className="step-circle">3</div>
              <div className="step-label">XLM-RoBERTa + RoBERTa</div>
              <div className="step-sub">Multilingual veracity evaluation & hate-speech classification</div>
            </div>

            <div className="flow-arrow">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M5 12H19M19 12L12 5M19 12L12 19" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>

            <div className="flow-step">
              <div className="step-circle">4</div>
              <div className="step-label">Standardized Verdict</div>
              <div className="step-sub">Calibrated verdict with source provenance</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
