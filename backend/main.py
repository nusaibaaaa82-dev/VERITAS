"""VERITAS FastAPI Application.

Main entry point for the VERITAS automated claim verification backend.
Integrates neural transformer adapters (XLM-RoBERTa fact-checking and RoBERTa hate-speech classification)
with hybrid evidence retrieval, standardized verdict assessment, and unified static frontend serving.

Launch Instructions:
From project root:
    uvicorn backend.main:app --host 0.0.0.0 --port 7860
Or run directly:
    python -m backend.main
"""

import logging
import os
from pathlib import Path
import sys
from typing import Optional

# Ensure project root is present in sys.path so 'backend.*' imports resolve
# consistently regardless of whether uvicorn is launched from the root or inside backend/
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.middleware.rate_limiter import SlidingWindowRateLimiter
from backend.schemas.claim import (
    ClaimReceiptResponse,
    ClaimRequest,
    ModelControlRequest,
    VerificationResultResponse,
)
from backend.services.verification import VerificationPipeline

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "VERITAS is a multilingual AI-powered claim verification platform. "
        "It integrates cross-lingual semantic representations (XLM-RoBERTa: 7-class & binary fact-checking) "
        "and safety classification (RoBERTa: immigrant hate-speech detection) alongside authoritative "
        "evidence retrieval to substantiate claims with scientific integrity.\n\n"
        "**Core Reliability Principles:**\n"
        "- Never fabricate predictions, confidence scores, or evidence sources.\n"
        "- Preserve both XLM-RoBERTa repositories as separate classification configurations.\n"
        "- Do not treat the RoBERTa hate-speech classifier as a fact-checking classifier.\n"
        "- Incompatible classification labels must never be combined to claim independent truth verification.\n"
        "- Conclusive verdicts require at least two independent verified sources.\n"
        "- Model agreement is never treated as proof of truth."
    ),
    version=settings.APP_VERSION,
)

# Configure CORS with configurable origins and restricted HTTP methods
configured_origins = list(settings.CORS_ORIGINS)
env_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
if env_origins:
    configured_origins.extend([orig.strip() for orig in env_origins.split(",") if orig.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)

# Apply in-memory sliding window rate limiter
app.add_middleware(
    SlidingWindowRateLimiter,
    requests_per_minute=getattr(settings, "RATE_LIMIT_REQUESTS_PER_MINUTE", 20),
    enabled=getattr(settings, "RATE_LIMIT_ENABLED", True),
)

# Global pipeline orchestrator
pipeline = VerificationPipeline()

# Static frontend assets configuration (for unified Hugging Face Spaces deployment)
_frontend_dist = _project_root / "frontend" / "dist"
_has_frontend = _frontend_dist.is_dir() and (_frontend_dist / "index.html").is_file()

if _has_frontend and (_frontend_dist / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Provide clear, beginner-friendly error messages for validation failures."""
    errors = []
    for err in exc.errors():
        field = " -> ".join(str(loc) for loc in err.get("loc", []))
        errors.append(f"{field}: {err.get('msg')}")

    return JSONResponse(
        status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
        content={
            "success": False,
            "error": "Validation Error",
            "details": errors,
            "status": "rejected",
        },
    )


if _has_frontend:
    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        fav_path = _frontend_dist / "favicon.svg"
        if fav_path.is_file():
            return FileResponse(str(fav_path), media_type="image/svg+xml")
        raise HTTPException(status_code=404, detail="Favicon not found")

    @app.get("/icons.svg", include_in_schema=False)
    def icons():
        icons_path = _frontend_dist / "icons.svg"
        if icons_path.is_file():
            return FileResponse(str(icons_path), media_type="image/svg+xml")
        raise HTTPException(status_code=404, detail="Icons not found")


@app.get(
    "/",
    summary="Application Root",
    description="Serves the VERITAS React frontend web application or API welcome message.",
    tags=["System"],
)
def home():
    """Root endpoint serving the interactive frontend when built, or API status fallback."""
    if _has_frontend:
        return FileResponse(str(_frontend_dist / "index.html"))
    return {
        "message": "Welcome to VERITAS API",
        "status": "running",
    }


@app.get(
    "/api",
    summary="API Info",
    description="Returns welcome message and operational status of the VERITAS API.",
    tags=["System"],
)
def api_info():
    """API informational root endpoint."""
    return {
        "message": "Welcome to VERITAS API",
        "status": "running",
        "version": settings.APP_VERSION,
    }


@app.api_route(
    "/health",
    methods=["GET", "HEAD"],
    summary="Health Check",
    description="Returns health status of the API service.",
    tags=["System"],
)
def health_check():
    """Health check endpoint for monitoring uptime."""
    return {
        "status": "healthy",
    }


@app.post(
    "/api/claims",
    response_model=ClaimReceiptResponse,
    status_code=status.HTTP_200_OK,
    summary="Receive Claim (Receipt Only)",
    description=(
        "Validates input text (≤ 1,000 characters, non-whitespace) and returns an honest "
        "receipt confirming the claim was captured. Does not generate fake verdicts or mock AI scores."
    ),
    tags=["Claims"],
)
def submit_claim(request: ClaimRequest):
    """Receive and validate claim statement without generating mock verdicts."""
    return {
        "success": True,
        "message": "Claim received. Verification services are not connected yet.",
        "claim": request.claim,
        "status": "pending",
    }


@app.post(
    "/api/verify",
    response_model=VerificationResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute Verification Pipeline",
    description=(
        "Executes the full VERITAS verification lifecycle:\n"
        "1. Claim Normalization\n"
        "2. Language Identification (with explicit uncertainty handling)\n"
        "3. Evidence Retrieval (strictly verified sources, returns empty if disconnected)\n"
        "4. XLM-RoBERTa Inference (7-class & binary fact-checking adapters, no fake predictions)\n"
        "5. RoBERTa Inference (immigrant hate-speech classifier, no fake predictions; not fact-checking)\n"
        "6. Evidence-Based Verdict Assessment (>= 2 independent verified sources required)\n\n"
        "If evidence is insufficient, strictly returns UNVERIFIED. "
        "A future scientifically valid dual-model fact-checking comparison requires compatible fact-checking outputs. "
        "Never invents fake confidence scores."
    ),
    tags=["Verification Pipeline"],
)
def verify_claim(request: ClaimRequest):
    """Execute end-to-end verification pipeline."""
    try:
        return pipeline.verify_claim(request)
    except Exception as exc:
        logger.error("Verification pipeline failure: %s", exc, exc_info=True)
        error_detail = (
            f"Verification pipeline error: {str(exc)}"
            if settings.DEBUG
            else "Internal verification pipeline error. Please check claim input and retry."
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail,
        ) from exc


@app.get(
    "/api/models/status",
    summary="Model Availability Status",
    description="Returns loading and operational status for XLM-RoBERTa (7-class & binary) and RoBERTa (hate speech) adapters.",
    tags=["Models"],
)
def get_models_status():
    """Inspect model adapter states."""
    return {
        "models": pipeline.model_manager.get_model_statuses(),
        "policy": {
            "prohibit_fake_predictions": True,
            "prohibit_fake_confidence_scores": True,
            "require_two_independent_verified_sources": True,
            "hate_speech_separate_from_fact_checking": True,
            "no_direct_model_to_verdict_mapping": True,
            "xlm_roberta_shared_base_architecture": True,
        },
    }


@app.post(
    "/api/models/load",
    summary="Load Neural Model Weights",
    description="Loads specified transformer weights into memory ('xlm_roberta_7class', 'xlm_roberta_binary', 'roberta_hate_speech', or 'all').",
    tags=["Models"],
)
def load_models(request: Optional[ModelControlRequest] = None):
    """Load model weights on demand."""
    target = (request.model_name if request else "all") or "all"
    if target.lower() == "all":
        results = pipeline.model_manager.load_all_models()
        return {
            "success": any(results.values()),
            "action": "load_all",
            "results": results,
            "models": pipeline.model_manager.get_model_statuses(),
        }
    else:
        ok = pipeline.model_manager.load_model(target)
        return {
            "success": ok,
            "action": f"load_{target}",
            "loaded": ok,
            "models": pipeline.model_manager.get_model_statuses(),
        }


@app.post(
    "/api/models/unload",
    summary="Unload Neural Model Weights",
    description="Unloads specified transformer weights from memory to reclaim RAM/VRAM.",
    tags=["Models"],
)
def unload_models(request: Optional[ModelControlRequest] = None):
    """Unload model weights on demand."""
    target = (request.model_name if request else "all") or "all"
    if target.lower() == "all":
        for k in ("xlm_roberta_7class", "xlm_roberta_binary", "roberta_hate_speech"):
            pipeline.model_manager.unload_model(k)
        return {
            "success": True,
            "action": "unload_all",
            "models": pipeline.model_manager.get_model_statuses(),
        }
    else:
        ok = pipeline.model_manager.unload_model(target)
        return {
            "success": ok,
            "action": f"unload_{target}",
            "models": pipeline.model_manager.get_model_statuses(),
        }


if __name__ == "__main__":
    import uvicorn
    # Default to port 7860 for Hugging Face Spaces compatibility, or use PORT env var
    port = int(os.getenv("PORT", "7860"))
    host = os.getenv("HOST", "0.0.0.0")
    logger.info("Starting VERITAS unified server on %s:%d", host, port)
    uvicorn.run("backend.main:app", host=host, port=port, reload=False)
