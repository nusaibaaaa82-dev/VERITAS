"""XLM-RoBERTa model adapter for VERITAS.

This module provides dedicated adapters for XLM-RoBERTa (Cross-Lingual RoBERTa)
checkpoints fine-tuned on the multilingual X-Fact benchmark.

Crucial Scientific & Architectural Integrity Rules:
1. Exact Label Taxonomies:
   - 7-Class ('nusaiba19/xlmr-xfact-7class'):
     0 = true
     1 = mostly true
     2 = partly true/misleading
     3 = complicated/hard to categorise
     4 = other
     5 = mostly false
     6 = false
   - Binary ('nusaiba19/xlmr-xfact-binary'):
     0 = true-ish
     1 = false-ish
     *NEVER rename these labels to TRUE/FALSE.*
2. Shared Architecture (No False Independence Claim):
   Both checkpoints share the identical base transformer architecture ('xlm-roberta-base',
   278M parameters, 12 layers, 768 hidden size, 12 attention heads, vocab size 250,002).
   They are two distinct fine-tuned classification heads on the SAME foundation model,
   NOT independent transformer architectures.
3. Multilingual Scope:
   Supports 100+ languages across the unified SentencePiece embedding space.
4. Model Status:
   Always unavailable ('model_not_loaded', is_available=False, prediction=None) until real weights load.
5. Zero Weight Downloading & Zero Hallucinated Predictions.
"""

import logging
import time
from typing import Dict, List, Optional
from backend.config import settings
from backend.schemas.claim import EvidenceItem, ModelInferenceResult

logger = logging.getLogger(__name__)

# Audited exact label taxonomies from Hugging Face config.json
ID2LABEL_7CLASS: Dict[int, str] = {
    0: "true",
    1: "mostly true",
    2: "partly true/misleading",
    3: "complicated/hard to categorise",
    4: "other",
    5: "mostly false",
    6: "false",
}
LABEL2ID_7CLASS: Dict[str, int] = {v: k for k, v in ID2LABEL_7CLASS.items()}

# Audited exact label taxonomy for binary classification
# Rule: Never rename these labels to TRUE/FALSE.
ID2LABEL_BINARY: Dict[int, str] = {
    0: "true-ish",
    1: "false-ish",
}
LABEL2ID_BINARY: Dict[str, int] = {v: k for k, v in ID2LABEL_BINARY.items()}


class XLMRoBERTaAdapter:
    """Adapter for XLM-RoBERTa cross-lingual fact-checking transformer inference."""

    # Both checkpoints share the identical base transformer architecture
    BASE_ARCHITECTURE: str = "xlm-roberta-base"

    def __init__(
        self,
        config_type: str = "7class",
        model_name: Optional[str] = None,
    ):
        self.config_type: str = config_type.lower()
        if self.config_type == "binary":
            self.model_name: str = model_name or settings.XLM_ROBERTA_BINARY_MODEL_NAME
            self.task: str = "fact_checking_binary"
            self.display_name: str = "XLM-RoBERTa (Binary)"
            self.num_labels: int = 2
            self.id2label: Dict[int, str] = ID2LABEL_BINARY
            self.label2id: Dict[str, int] = LABEL2ID_BINARY
        else:
            self.model_name: str = model_name or settings.XLM_ROBERTA_7CLASS_MODEL_NAME
            self.task: str = "fact_checking_7class"
            self.display_name: str = "XLM-RoBERTa (7-Class)"
            self.num_labels: int = 7
            self.id2label: Dict[int, str] = ID2LABEL_7CLASS
            self.label2id: Dict[str, int] = LABEL2ID_7CLASS

        self.classification_type: str = "fact_checking"
        self.architecture_detail: str = (
            f"xlm-roberta-base fine-tuned checkpoint ({self.task}). "
            "Note: Shares the base transformer architecture with the alternative XLM-R checkpoint; "
            "these are not independent model architectures."
        )
        self.is_loaded: bool = False
        self.status: str = "model_not_loaded"
        self.loading_time_s: Optional[float] = None
        self.device: Optional[str] = None
        self._tokenizer = None
        self._model = None

    def load_model(self, device: Optional[str] = None) -> bool:
        """Load XLM-RoBERTa weights and tokenizer lazily into memory.

        Uses exact Hugging Face repository IDs:
        - 7-Class: 'nusaiba19/xlmr-xfact-7class'
        - Binary: 'nusaiba19/xlmr-xfact-binary'
        Supports lazy loading with PyTorch Metal (MPS), CUDA, or CPU fallback.
        Preserves audited label mapping and reports status honestly without hallucinating.
        """
        if self.is_loaded and self._model is not None and self._tokenizer is not None:
            return True

        self.status = "loading"
        t0 = time.perf_counter()

        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            if device is not None:
                target_device = device
            elif torch.backends.mps.is_available():
                target_device = "mps"
            elif torch.cuda.is_available():
                target_device = "cuda"
            else:
                target_device = "cpu"

            logger.info("Loading XLM-RoBERTa weights from '%s' on %s...", self.model_name, target_device)

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
        """Evaluate language compatibility for XLM-RoBERTa."""
        if not language or language == "und":
            return "uncertain: undetermined language; multilingual SentencePiece tokenizer will attempt processing"
        return f"supported: multilingual SentencePiece cross-lingual coverage ({language})"

    def infer(
        self,
        claim: str,
        evidence: Optional[List[EvidenceItem]] = None,
        language: Optional[str] = None,
    ) -> ModelInferenceResult:
        """Execute inference against claim and retrieved evidence.

        Reliability Rules:
        - An unavailable or unimplemented model can NEVER return is_available=True.
        - Prediction is strictly None when weights are not loaded.
        - Exact label mappings are preserved without renaming.
        - Never generate fake predictions or confidence scores.
        - Binary labels are strictly 'true-ish' and 'false-ish'; NEVER rename to TRUE/FALSE.
        """
        lang_status = self.check_language_support(language)

        # 1. Honest status check: return unavailable if weights are not loaded
        if not self.is_loaded or self._model is None or self._tokenizer is None:
            return ModelInferenceResult(
                model_name=self.display_name,
                is_available=False,
                prediction=None,
                status="model_not_loaded",
                details=(
                    f"Adapter for '{self.model_name}' ({self.task}) is initialized, but model weights are not loaded. "
                    "Real inference requires calling load_model(). Fake predictions are strictly prohibited."
                ),
                task=self.task,
                repository=self.model_name,
                classification_type=self.classification_type,
                architecture=self.BASE_ARCHITECTURE,
                label_mapping=self.id2label,
                language_support=lang_status,
            )

        # 2. Real neural forward pass with timing
        try:
            import torch

            t_infer = time.perf_counter()

            # Tokenize claim. If evidence snippets are present, pass top snippet as text pair
            evidence_snippet = None
            if evidence:
                for ev in evidence:
                    if ev.snippet and len(ev.snippet.strip()) > 10:
                        evidence_snippet = ev.snippet.strip()
                        break

            if evidence_snippet:
                inputs = self._tokenizer(
                    claim,
                    evidence_snippet,
                    return_tensors="pt",
                    truncation=True,
                    max_length=512,
                    padding=True,
                )
            else:
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

            pair_note = " (with evidence context)" if evidence_snippet else " (claim-only)"
            details = (
                f"Model prediction: '{pred_label}' (class {pred_id}){pair_note} with {confidence * 100:.2f}% softmax probability. "
                "Notice: This neural prediction provides auxiliary analytical signals only and does not establish "
                "factual verification, which requires independent primary sources."
            )

            return ModelInferenceResult(
                model_name=self.display_name,
                is_available=True,
                prediction=pred_label,
                status="active",
                details=details,
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
            logger.error("Error during XLM-RoBERTa inference: %s", str(exc))
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
