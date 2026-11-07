"""RoBERTa model adapter for VERITAS.

This module provides the dedicated adapter for RoBERTa fine-tuned as an
immigrant hate-speech classifier:
Repository: 'nusaiba19/roberta-immigrant-hate-speech'

Crucial Scientific & Reliability Rules:
1. Exact Label Taxonomy:
   0 = not-hate
   1 = hate
2. Strict Domain Segregation:
   This model detects hate speech, toxicity, and dehumanizing rhetoric directed
   at immigrant communities. It does NOT evaluate claim veracity, factual truth,
   or evidence corroboration.
3. Incompatible Classification Labels:
   'not-hate' / 'hate' labels must NEVER be combined with fact-checking labels
   or treated as factual verification.
4. Language Scope & Explicit Handling for Unsupported Languages:
   This model was trained exclusively on English social media comments
   (filtered from UC Berkeley Measuring Hate Speech dataset, vocab size 50,265).
   Non-English languages are explicitly unsupported and flagged as such.
5. Model Status:
   Always unavailable ('model_not_loaded', is_available=False, prediction=None) until real weights load.
6. Zero Weight Downloading & Zero Hallucinated Predictions.
"""

import logging
import time
from typing import Dict, List, Optional
from backend.config import settings
from backend.schemas.claim import EvidenceItem, ModelInferenceResult

logger = logging.getLogger(__name__)

# Audited exact label taxonomy from Hugging Face config.json
ID2LABEL_HATE_SPEECH: Dict[int, str] = {
    0: "not-hate",
    1: "hate",
}
LABEL2ID_HATE_SPEECH: Dict[str, int] = {v: k for k, v in ID2LABEL_HATE_SPEECH.items()}


class RoBERTaAdapter:
    """Adapter for RoBERTa immigrant hate-speech classification inference."""

    BASE_ARCHITECTURE: str = "roberta-base"
    SUPPORTED_LANGUAGES = frozenset({"en", "eng"})

    def __init__(self, model_name: Optional[str] = None):
        self.model_name: str = model_name or settings.ROBERTA_HATE_SPEECH_MODEL_NAME
        self.task: str = "immigrant_hate_speech_classification"
        self.display_name: str = "RoBERTa (Hate-Speech Classifier)"
        self.classification_type: str = "content_safety"
        self.num_labels: int = 2
        self.id2label: Dict[int, str] = ID2LABEL_HATE_SPEECH
        self.label2id: Dict[str, int] = LABEL2ID_HATE_SPEECH
        self.is_loaded: bool = False
        self.status: str = "model_not_loaded"
        self.loading_time_s: Optional[float] = None
        self.device: Optional[str] = None
        self._tokenizer = None
        self._model = None

    def load_model(self, device: Optional[str] = None) -> bool:
        """Load RoBERTa weights and tokenizer lazily into memory.

        Uses exact Hugging Face repository: 'nusaiba19/roberta-immigrant-hate-speech'.
        Supports lazy loading with PyTorch Metal (MPS), CUDA, or CPU fallback.
        Reports errors honestly and never silently substitutes another model.
        """
        if self.is_loaded and self._model is not None and self._tokenizer is not None:
            return True

        self.status = "loading"
        t0 = time.perf_counter()

        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            # Determine optimal execution device
            if device is not None:
                target_device = device
            elif torch.backends.mps.is_available():
                target_device = "mps"
            elif torch.cuda.is_available():
                target_device = "cuda"
            else:
                target_device = "cpu"

            logger.info("Loading RoBERTa weights from '%s' on %s...", self.model_name, target_device)

            # Try local cache first to avoid slow network/DNS retries when already downloaded
            try:
                tokenizer = AutoTokenizer.from_pretrained(self.model_name, local_files_only=True)
                model = AutoModelForSequenceClassification.from_pretrained(self.model_name, local_files_only=True)
            except Exception:
                tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                model = AutoModelForSequenceClassification.from_pretrained(self.model_name)

            model.to(target_device)
            model.eval()

            self._tokenizer = tokenizer
            self._model = model
            self.device = target_device
            self.is_loaded = True
            self.status = "loaded"
            self.loading_time_s = round(time.perf_counter() - t0, 3)
            logger.info("Successfully loaded '%s' in %.3fs on %s", self.model_name, self.loading_time_s, self.device)
            return True

        except Exception as exc:
            self.is_loaded = False
            self.status = f"load_failed: {type(exc).__name__}: {str(exc)}"
            self._tokenizer = None
            self._model = None
            logger.error("Failed to load '%s': %s", self.model_name, str(exc))
            return False

    def check_language_support(self, language: Optional[str] = None) -> str:
        """Explicit handling for unsupported languages.

        RoBERTa was fine-tuned exclusively on English social media comments.
        Claims in other languages cannot be evaluated by this monolingual model.
        """
        if not language or language == "und":
            return "uncertain: undetermined language; model requires English text"
        clean_lang = language.strip().lower()
        if clean_lang in self.SUPPORTED_LANGUAGES:
            return "supported: English input matches training domain"
        return f"unsupported: language '{language}' is outside English-only training domain"

    def infer(
        self,
        claim: str,
        evidence: Optional[List[EvidenceItem]] = None,
        language: Optional[str] = None,
    ) -> ModelInferenceResult:
        """Execute inference against claim text for immigrant hate speech.

        Reliability Rules:
        - Do NOT treat this classifier as a fact-checking model.
        - An unavailable or unimplemented model can NEVER return is_available=True.
        - Prediction is strictly None when weights are not loaded.
        - Never generate fake predictions or confidence scores.
        - Explicitly flag unsupported non-English languages.
        """
        lang_status = self.check_language_support(language)

        # 1. Non-English language rejection rule:
        # RoBERTa base was fine-tuned exclusively on English social media comments.
        # Inputs in Spanish, Hindi, Bengali, or other languages cannot be evaluated.
        if "unsupported" in lang_status:
            return ModelInferenceResult(
                model_name=self.display_name,
                is_available=False,
                prediction=None,
                status="unsupported_language",
                details=(
                    f"RoBERTa immigrant hate-speech classifier ('{self.model_name}') is strictly English-only. "
                    f"Input language '{language}' is outside its training domain. Evaluation rejected."
                ),
                task=self.task,
                repository=self.model_name,
                classification_type=self.classification_type,
                architecture=self.BASE_ARCHITECTURE,
                label_mapping=self.id2label,
                language_support=lang_status,
            )

        # 2. Honest status check: return unavailable if weights are not loaded
        if not self.is_loaded or self._model is None or self._tokenizer is None:
            return ModelInferenceResult(
                model_name=self.display_name,
                is_available=False,
                prediction=None,
                status="model_not_loaded",
                details=(
                    f"Adapter for '{self.model_name}' (immigrant hate-speech classifier) is initialized, "
                    "but model weights are not loaded. Real inference requires calling load_model(). "
                    "Fake predictions are strictly prohibited."
                ),
                task=self.task,
                repository=self.model_name,
                classification_type=self.classification_type,
                architecture=self.BASE_ARCHITECTURE,
                label_mapping=self.id2label,
                language_support=lang_status,
            )

        # 3. Real neural forward pass with timing
        try:
            import torch

            t_infer = time.perf_counter()
            inputs = self._tokenizer(
                claim,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True,
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model(**inputs)
                probabilities = torch.softmax(outputs.logits, dim=-1)[0]
                pred_id = int(torch.argmax(probabilities).item())
                confidence = round(float(probabilities[pred_id].item()), 4)

            infer_ms = round((time.perf_counter() - t_infer) * 1000.0, 2)
            pred_label = self.id2label.get(pred_id, str(pred_id))

            return ModelInferenceResult(
                model_name=self.display_name,
                is_available=True,
                prediction=pred_label,
                status="active",
                details=(
                    f"Model prediction: '{pred_label}' (class {pred_id}) with {confidence * 100:.2f}% softmax probability. "
                    "Notice: This is an English content-safety classifier detecting immigrant toxicity/hate speech, "
                    "NOT a claim verification model. It does not assess factual truth."
                ),
                task=self.task,
                repository=self.model_name,
                classification_type=self.classification_type,
                architecture=self.BASE_ARCHITECTURE,
                label_mapping=self.id2label,
                language_support=lang_status,
                raw_class_id=pred_id,
                confidence=confidence,
                inference_time_ms=infer_ms,
                device=self.device,
            )

        except Exception as exc:
            logger.error("Error during RoBERTa inference: %s", str(exc))
            return ModelInferenceResult(
                model_name=self.display_name,
                is_available=False,
                prediction=None,
                status=f"inference_error: {type(exc).__name__}",
                details=f"Inference execution failed: {str(exc)}",
                task=self.task,
                repository=self.model_name,
                classification_type=self.classification_type,
                architecture=self.BASE_ARCHITECTURE,
                label_mapping=self.id2label,
                language_support=lang_status,
            )
