export const Footer = () => {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="footer">
      <div className="footer-container">
        <div className="footer-top">
          {/* Brand Column */}
          <div className="footer-brand-col">
            <div className="footer-brand">
              <div className="logo-icon-wrapper">
                <svg
                  className="logo-icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                  aria-hidden="true"
                >
                  <path
                    d="M12 2L20 6V12C20 16.97 16.59 21.5 12 22.5C7.41 21.5 4 16.97 4 12V6L12 2Z"
                    fill="#EDF1F0"
                    stroke="#267C78"
                    strokeWidth="1.75"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M9 12L11 14L15 10"
                    stroke="#267C78"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
              <span className="footer-brand-name">VERITAS</span>
            </div>
            <p className="footer-tagline">Truth deserves verification.</p>
            <p className="footer-brand-desc">
              An advanced AI-powered claim verification platform engineered to detect
              misinformation, analyze stance, and validate evidence using state-of-the-art
              multilingual transformer ensembles.
            </p>
          </div>

          {/* Quick Links Column */}
          <div className="footer-links-col">
            <h4 className="footer-heading">Navigation</h4>
            <ul className="footer-link-list">
              <li>
                <a href="#home">Home</a>
              </li>
              <li>
                <a href="#how-it-works">How It Works</a>
              </li>
              <li>
                <a href="#verdicts">Verdicts</a>
              </li>
              <li>
                <a href="#technology">Technology</a>
              </li>
              <li>
                <a href="#about">About VERITAS</a>
              </li>
            </ul>
          </div>

          {/* Architecture Column */}
          <div className="footer-links-col">
            <h4 className="footer-heading">AI Architecture</h4>
            <ul className="footer-link-list">
              <li>
                <a href="#technology">XLM-RoBERTa (Cross-Lingual)</a>
              </li>
              <li>
                <a href="#technology">RoBERTa (Hate Speech Classifier)</a>
              </li>
              <li>
                <a href="#technology">Dense & BM25 Retrieval</a>
              </li>
              <li>
                <a href="#technology">Stance & Stance Calibration</a>
              </li>
              <li>
                <a href="#verdicts">5-Verdict Taxonomy</a>
              </li>
            </ul>
          </div>

          {/* Verdicts Column */}
          <div className="footer-links-col">
            <h4 className="footer-heading">Verdicts</h4>
            <ul className="footer-link-list">
              <li>
                <a href="#verdicts">TRUE</a>
              </li>
              <li>
                <a href="#verdicts">FALSE</a>
              </li>
              <li>
                <a href="#verdicts">PARTIALLY TRUE</a>
              </li>
              <li>
                <a href="#verdicts">MISLEADING</a>
              </li>
              <li>
                <a href="#verdicts">UNVERIFIED</a>
              </li>
            </ul>
          </div>
        </div>

        <div className="footer-divider" />

        <div className="footer-bottom">
          <div className="footer-copyright">
            © {currentYear} VERITAS. All rights reserved. Truth deserves verification.
          </div>
          <div className="footer-disclaimer">
            Built with modern NLP research (XLM-RoBERTa & RoBERTa). Designed for non-partisan factual integrity.
          </div>
        </div>
      </div>
    </footer>
  );
};

