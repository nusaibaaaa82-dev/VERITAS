export const About = () => {
  return (
    <section id="about" className="about-section">
      <div className="section-container">
        <div className="about-grid">
          <div className="about-content">
            <span className="section-badge">Our Mission</span>
            <h2 className="section-title">Truth Deserves Verification</h2>
            <p className="about-lead">
              In an era overwhelmed by algorithmic echo chambers, coordinated disinformation, and
              AI-generated hallucinations, discerning truth from distortion has become one of
              humanity&apos;s greatest challenges.
            </p>
            <p className="about-text">
              <strong>VERITAS</strong> was created on a single, uncompromising principle: claims
              must be substantiated with traceable evidence, not consensus sentiment or black-box
              assumptions. By combining rigorous multilingual natural language processing (XLM-RoBERTa
              and RoBERTa) with real-time retrieval across trusted repositories, VERITAS delivers
              objective claim verification designed for journalists, researchers, and truth-seekers
              worldwide.
            </p>

            <div className="pillars-grid">
              <div className="pillar-item">
                <div className="pillar-icon-box">
                  <svg viewBox="0 0 24 24" fill="none" stroke="#267C78" strokeWidth="2">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  </svg>
                </div>
                <div>
                  <h4 className="pillar-title">Non-Partisan & Objective</h4>
                  <p className="pillar-desc">
                    Evaluations are governed strictly by empirical data and primary source alignment.
                  </p>
                </div>
              </div>

              <div className="pillar-item">
                <div className="pillar-icon-box">
                  <svg viewBox="0 0 24 24" fill="none" stroke="#267C78" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="2" y1="12" x2="22" y2="12" />
                    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                  </svg>
                </div>
                <div>
                  <h4 className="pillar-title">Multilingual Equity</h4>
                  <p className="pillar-desc">
                    Engineered to verify claims across 100+ languages without cultural or Western bias.
                  </p>
                </div>
              </div>

              <div className="pillar-item">
                <div className="pillar-icon-box">
                  <svg viewBox="0 0 24 24" fill="none" stroke="#267C78" strokeWidth="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="16" y1="13" x2="8" y2="13" />
                    <line x1="16" y1="17" x2="8" y2="17" />
                    <polyline points="10 9 9 9 8 9" />
                  </svg>
                </div>
                <div>
                  <h4 className="pillar-title">Complete Provenance</h4>
                  <p className="pillar-desc">
                    Every verdict provides auditable citations back to primary ground-truth documents.
                  </p>
                </div>
              </div>

              <div className="pillar-item">
                <div className="pillar-icon-box">
                  <svg viewBox="0 0 24 24" fill="none" stroke="#267C78" strokeWidth="2">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                  </svg>
                </div>
                <div>
                  <h4 className="pillar-title">Open Science Commitment</h4>
                  <p className="pillar-desc">
                    Advancing research in automated fact-checking, natural language inference, and epistemic security.
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="about-aside">
            <div className="aside-card">
              <div className="aside-quote-icon">“</div>
              <blockquote className="aside-quote">
                Without verifiable facts, democratic discourse deteriorates into competing fictions.
                Verification is not censorship—it is illumination.
              </blockquote>
              <div className="aside-author">
                <span className="author-name">The VERITAS Research Initiative</span>
                <span className="author-role">Information Integrity & NLP Lab</span>
              </div>

              <div className="aside-stats-box">
                <div className="aside-stat">
                  <span className="stat-num">100+</span>
                  <span className="stat-label">Cross-Lingual Vectors</span>
                </div>
                <div className="aside-stat">
                  <span className="stat-num">5</span>
                  <span className="stat-label">Standardized Verdicts</span>
                </div>
                <div className="aside-stat">
                  <span className="stat-num">0%</span>
                  <span className="stat-label">Hallucinated Evidence</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

