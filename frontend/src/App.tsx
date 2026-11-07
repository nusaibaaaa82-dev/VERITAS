import { useRef } from 'react';
import { Navbar } from './components/Navbar';
import { Hero } from './components/Hero';
import { HowItWorks } from './components/HowItWorks';
import { Verdicts } from './components/Verdicts';
import { Technology } from './components/Technology';
import { About } from './components/About';
import { Footer } from './components/Footer';
import './App.css';

function App() {
  const claimInputRef = useRef<HTMLTextAreaElement | null>(null);

  const handleGetStartedClick = () => {
    if (claimInputRef.current) {
      claimInputRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
      claimInputRef.current.focus();
    } else {
      const verifyElement = document.getElementById('verify');
      if (verifyElement) {
        verifyElement.scrollIntoView({ behavior: 'smooth' });
      }
    }
  };

  return (
    <div className="veritas-app">
      <Navbar onGetStartedClick={handleGetStartedClick} />
      <main className="main-content">
        <Hero inputRef={claimInputRef} />
        <HowItWorks />
        <Verdicts />
        <Technology />
        <About />
      </main>
      <Footer />
    </div>
  );
}

export default App;
