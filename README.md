---
title: VERITAS — Multilingual AI Claim Verification
emoji: ⚖️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Multilingual AI fact-checking and authoritative evidence retrieval.
---

# VERITAS — Truth Deserves Verification

**VERITAS** is a multilingual AI-powered claim verification platform combining cross-lingual transformer inference with authoritative evidence retrieval across English, Spanish, Hindi, and Bengali.

---

## 🌟 Key Capabilities

1. **Multilingual Claim Normalization & Language Identification:**
   - Detects English, Spanish, Hindi, and Bengali with lexical marker verification and uncertainty handling.
   - Cleans diacritics, zero-width characters, and Unicode discrepancies without altering semantic intent.
2. **Rule-Based Claim Decomposition:**
   - Syntactically parses complex multi-clause sentences into atomic factual propositions (entity, quantitative, temporal, causal).
   - Validates numerical assertions and chronological bounds against retrieved evidence.
3. **Multi-Source Authoritative Retrieval:**
   - Connects to verified, free public APIs: **World Bank (WDS)**, **WHO IRIS (OAI-PMH)**, **PubMed**, **OpenAlex**, **Crossref**, **NASA NTRS**, and **USGS**.
   - Leverages a local SQLite repository with FTS5 full-text search and WAL journal mode.
4. **Independent Stance & Provenance Safeguards:**
   - Requires at least two independent primary verified sources to substantiate a claim.
   - Strictly collapses translated copies into a single vote.
   - Separates unverified literature matches from verified empirical corroboration.
5. **Audited Neural Transformer Adapters (CPU-Optimized):**
   - **XLM-RoBERTa (7-Class):** Multilingual fact-checking (`nusaiba19/xlmr-xfact-7class`).
   - **XLM-RoBERTa (Binary):** Multilingual fact-checking (`nusaiba19/xlmr-xfact-binary`).
   - **RoBERTa (Content Safety):** Specialized immigrant hate-speech classifier (`nusaiba19/roberta-immigrant-hate-speech`).
   - Zero hallucinated scores or fake predictions: models remain unloaded until requested and report honest confidence.

---

## 🏗️ Architecture & Deployment

VERITAS runs as a single unified container:
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS.
- **Backend:** FastAPI, Uvicorn, SQLite FTS5, PyTorch CPU.
- **Deployment Target:** Hugging Face Docker Space (`sdk: docker`, port `7860`).

### Local Development

#### Prerequisites
- Node.js 20+ and npm
- Python 3.10+ (with virtual environment)

#### 1. Start the Backend
```bash
# Navigate to backend and activate virtualenv
cd backend
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run FastAPI server on port 8000 (or 7860)
uvicorn main:app --reload --port 8000
```

#### 2. Start the Frontend
```bash
# In a separate terminal
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173` to explore the interactive interface.

---

## 🚀 Deploying to Hugging Face Spaces

1. Create a new Space on [Hugging Face](https://huggingface.co/new-space).
2. Choose **Docker** as the Space SDK and select the free **CPU basic (2 vCPU, 16 GB RAM)** tier.
3. Clone your Space repository locally:
   ```bash
   git clone https://huggingface.co/spaces/<YOUR_USERNAME>/<YOUR_SPACE_NAME>
   ```
4. Copy the repository contents into your Space folder:
   ```bash
   cp Dockerfile .dockerignore README.md /path/to/your/space/
   cp -r backend frontend /path/to/your/space/
   ```
5. Commit and push:
   ```bash
   cd /path/to/your/space/
   git add .
   git commit -m "Deploy VERITAS unified Docker container"
   git push
   ```
6. Hugging Face will automatically build and launch your container on port `7860`.

---

## 🛡️ Reliability Guarantees

- **No Fabricated Confidence Scores:** Predictions are strictly derived from loaded model checkpoints.
- **No False Consensus:** Agreement between the two XLM-RoBERTa checkpoints is never presented as independent proof, because both fine-tuned heads share the foundation `xlm-roberta-base` architecture.
- **Strict Evidence Floor:** Conclusive verdicts (`TRUE` or `FALSE`) strictly require corroboration from $\ge 2$ independent verified sources.
- **Safe Rate Limiting:** Enforces 20 requests per minute per IP with reverse-proxy IP spoofing prevention (`cf-connecting-ip`, `x-real-ip`).

---

## 📄 License
MIT License.
