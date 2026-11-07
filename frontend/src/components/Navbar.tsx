import { useState, useEffect } from 'react';

interface NavbarProps {
  onGetStartedClick: () => void;
}

export const Navbar = ({ onGetStartedClick }: NavbarProps) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const toggleMobileMenu = () => {
    setIsMobileMenuOpen((prev) => !prev);
  };

  const closeMobileMenu = () => {
    setIsMobileMenuOpen(false);
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isMobileMenuOpen) {
        setIsMobileMenuOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isMobileMenuOpen]);

  return (
    <header className="header">
      <div className="header-container">
        <a href="#home" className="brand-logo" onClick={closeMobileMenu}>
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
          <div className="brand-text-group">
            <span className="brand-name">VERITAS</span>
            <span className="brand-badge">AI FACT-CHECK</span>
          </div>
        </a>

        {/* Desktop Navigation */}
        <nav className="desktop-nav" aria-label="Main Navigation">
          <ul className="nav-links">
            <li>
              <a href="#home" className="nav-link">
                Home
              </a>
            </li>
            <li>
              <a href="#how-it-works" className="nav-link">
                How It Works
              </a>
            </li>
            <li>
              <a href="#verdicts" className="nav-link">
                Verdicts
              </a>
            </li>
            <li>
              <a href="#technology" className="nav-link">
                Technology
              </a>
            </li>
            <li>
              <a href="#about" className="nav-link">
                About
              </a>
            </li>
          </ul>
        </nav>

        <div className="header-actions">
          <button
            type="button"
            className="btn btn-primary nav-cta-btn"
            onClick={onGetStartedClick}
          >
            <span>Get Started</span>
            <svg
              className="btn-arrow"
              viewBox="0 0 16 16"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M3.33334 8H12.6667M12.6667 8L8.00001 3.33334M12.6667 8L8.00001 12.6667"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>

          {/* Mobile menu toggle */}
          <button
            type="button"
            className="mobile-toggle"
            onClick={toggleMobileMenu}
            aria-label={isMobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={isMobileMenuOpen}
          >
            <span className={`hamburger-bar ${isMobileMenuOpen ? 'open-1' : ''}`} />
            <span className={`hamburger-bar ${isMobileMenuOpen ? 'open-2' : ''}`} />
            <span className={`hamburger-bar ${isMobileMenuOpen ? 'open-3' : ''}`} />
          </button>
        </div>
      </div>

      {/* Mobile Dropdown Nav */}
      {isMobileMenuOpen && (
        <div className="mobile-nav-panel">
          <nav aria-label="Mobile Navigation">
            <ul className="mobile-nav-links">
              <li>
                <a href="#home" className="mobile-nav-link" onClick={closeMobileMenu}>
                  Home
                </a>
              </li>
              <li>
                <a href="#how-it-works" className="mobile-nav-link" onClick={closeMobileMenu}>
                  How It Works
                </a>
              </li>
              <li>
                <a href="#verdicts" className="mobile-nav-link" onClick={closeMobileMenu}>
                  Verdicts
                </a>
              </li>
              <li>
                <a href="#technology" className="mobile-nav-link" onClick={closeMobileMenu}>
                  Technology
                </a>
              </li>
              <li>
                <a href="#about" className="mobile-nav-link" onClick={closeMobileMenu}>
                  About
                </a>
              </li>
            </ul>
            <div className="mobile-nav-actions">
              <button
                type="button"
                className="btn btn-primary w-full"
                onClick={() => {
                  closeMobileMenu();
                  onGetStartedClick();
                }}
              >
                <span>Get Started</span>
                <svg
                  className="btn-arrow"
                  viewBox="0 0 16 16"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    d="M3.33334 8H12.6667M12.6667 8L8.00001 3.33334M12.6667 8L8.00001 12.6667"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
};

