"""Model Manager orchestrating multi-model neural architecture for VERITAS.

Coordinates XLM-RoBERTa (7-class and binary configurations) and RoBERTa (immigrant hate speech),
strictly enforcing VERITAS scientific integrity principles:
1. Exact Label Taxonomies:
   - XLM-RoBERTa 7-class: {0: 'true', 1: 'mostly true', 2: 'partly true/misleading',
     3: 'complicated/hard to categorise', 4: 'other', 5: 'mostly false', 6: 'false'}
   - XLM-RoBERTa binary: {0: 'true-ish', 1: 'false-ish'} (Never renamed to TRUE/FALSE)
   - RoBERTa: {0: 'not-hate', 1: 'hate'}
2. Architecture Clarification (No False Independence Claim):
   Both XLM-RoBERTa checkpoints share the identical base transformer architecture ('xlm-roberta-base').
   They are two distinct fine-tuned classification heads on the same foundation model, NOT
   two independent transformer architectures.
3. Strict Task & Domain Segregation:
   Do NOT treat the RoBERTa hate-speech classifier ('nusaiba19/roberta-immigrant-hate-speech')
   as a fact-checking classifier. It is an English content-safety classifier.
4. Tripartite Pipeline Distinction:
   Preserve strict separation between:
   - Model prediction (auxiliary analytical signals from neural adapters)
   - Evidence assessment (deduplicated, verified primary source corroboration)
   - Final VERITAS verdict (formulated solely by VerdictEngine anchored in verified evidence)
   Model predictions must NEVER be mapped directly to final verdicts.
5. Incompatible Classification Labels:
   Incompatible label spaces ('true-ish'/'false-ish' vs 7-class vs 'not-hate'/'hate') must
   never be merged or claimed to independently verify truth.
6. Language Handling:
   RoBERTa is strictly English-only; non-English inputs are explicitly flagged as unsupported.
7. Model Status:
   Always unavailable ('model_not_loaded', is_available=False, prediction=None) until real weights load.
"""

import gc
import logging
from typing import Dict, List, Optional, Tuple
from backend.config import settings
from backend.models.roberta import RoBERTaAdapter
from backend.models.xlm_roberta import XLMRoBERTaAdapter
from backend.schemas.claim import ComparisonStatus, EvidenceItem, ModelInferenceResult

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages and coordinates execution across all neural transformer adapters."""

    def __init__(self):
        # 1. XLM-RoBERTa 7-class fact-checking configuration (xlm-roberta-base)
        self.xlm_roberta_7class = XLMRoBERTaAdapter(
            config_type="7class",
            model_name=settings.XLM_ROBERTA_7CLASS_MODEL_NAME,
        )
        # 2. XLM-RoBERTa binary fact-checking configuration (xlm-roberta-base)
        self.xlm_roberta_binary = XLMRoBERTaAdapter(
            config_type="binary",
            model_name=settings.XLM_ROBERTA_BINARY_MODEL_NAME,
        )
        # 3. RoBERTa immigrant hate-speech classifier (roberta-base, English content safety)
        self.roberta_hate_speech = RoBERTaAdapter(
            model_name=settings.ROBERTA_HATE_SPEECH_MODEL_NAME,
        )

    def load_model(self, model_key: str, device: Optional[str] = None) -> bool:
        """Lazily load a specific model by key name.

        Supported keys:
        - 'xlm_roberta_7class', '7class', 'xlmr-7class'
        - 'xlm_roberta_binary', 'binary', 'xlmr-binary'
        - 'roberta_hate_speech', 'roberta', 'hate_speech'
        """
        key = model_key.lower().strip().replace("-", "_")
        if key in ("xlm_roberta_7class", "7class", "xlmr_7class"):
            return self.xlm_roberta_7class.load_model(device=device)
        elif key in ("xlm_roberta_binary", "binary", "xlmr_binary"):
            return self.xlm_roberta_binary.load_model(device=device)
        elif key in ("roberta_hate_speech", "roberta", "hate_speech"):
            return self.roberta_hate_speech.load_model(device=device)
        else:
            logger.warning("Unrecognized model key '%s' requested for loading.", model_key)
            return False

    def load_all_models(self, device: Optional[str] = None) -> Dict[str, bool]:
        """Lazily load all configured neural models into memory."""
        return {
            "XLM-RoBERTa-7Class": self.xlm_roberta_7class.load_model(device=device),
            "XLM-RoBERTa-Binary": self.xlm_roberta_binary.load_model(device=device),
            "RoBERTa-HateSpeech": self.roberta_hate_speech.load_model(device=device),
        }

    def unload_model(self, model_key: str) -> bool:
        """Unload model from memory to conserve RAM/VRAM."""
        key = model_key.lower().strip().replace("-", "_")
        adapter = None
        if key in ("xlm_roberta_7class", "7class", "xlmr_7class"):
            adapter = self.xlm_roberta_7class
        elif key in ("xlm_roberta_binary", "binary", "xlmr_binary"):
            adapter = self.xlm_roberta_binary
        elif key in ("roberta_hate_speech", "roberta", "hate_speech"):
            adapter = self.roberta_hate_speech

        if adapter:
            adapter._model = None
            adapter._tokenizer = None
            adapter.is_loaded = False
            adapter.status = "model_not_loaded"
            adapter.device = None
            gc.collect()
            try:
                import torch
                if torch.backends.mps.is_available():
                    torch.mps.empty_cache()
                elif torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            return True
        return False

    def get_model_statuses(self) -> Dict[str, Dict[str, object]]:
        """Return operational availability of all registered models with audited configurations."""
        return {
            "XLM-RoBERTa-7Class": {
                "model_name": self.xlm_roberta_7class.model_name,
                "display_name": self.xlm_roberta_7class.display_name,
                "base_architecture": self.xlm_roberta_7class.BASE_ARCHITECTURE,
                "architecture_note": "Shares base transformer architecture (xlm-roberta-base) with binary checkpoint.",
                "task": self.xlm_roberta_7class.task,
                "classification_type": self.xlm_roberta_7class.classification_type,
                "num_labels": self.xlm_roberta_7class.num_labels,
                "label_mapping": self.xlm_roberta_7class.id2label,
                "is_loaded": self.xlm_roberta_7class.is_loaded,
                "status": self.xlm_roberta_7class.status,
                "loading_time_s": getattr(self.xlm_roberta_7class, "loading_time_s", None),
                "device": getattr(self.xlm_roberta_7class, "device", None),
            },
            "XLM-RoBERTa-Binary": {
                "model_name": self.xlm_roberta_binary.model_name,
                "display_name": self.xlm_roberta_binary.display_name,
                "base_architecture": self.xlm_roberta_binary.BASE_ARCHITECTURE,
                "architecture_note": "Shares base transformer architecture (xlm-roberta-base) with 7-class checkpoint.",
                "task": self.xlm_roberta_binary.task,
                "classification_type": self.xlm_roberta_binary.classification_type,
                "num_labels": self.xlm_roberta_binary.num_labels,
                "label_mapping": self.xlm_roberta_binary.id2label,
                "is_loaded": self.xlm_roberta_binary.is_loaded,
                "status": self.xlm_roberta_binary.status,
                "loading_time_s": getattr(self.xlm_roberta_binary, "loading_time_s", None),
                "device": getattr(self.xlm_roberta_binary, "device", None),
            },
            "RoBERTa-HateSpeech": {
                "model_name": self.roberta_hate_speech.model_name,
                "display_name": self.roberta_hate_speech.display_name,
                "base_architecture": self.roberta_hate_speech.BASE_ARCHITECTURE,
                "task": self.roberta_hate_speech.task,
                "classification_type": self.roberta_hate_speech.classification_type,
                "supported_languages": list(self.roberta_hate_speech.SUPPORTED_LANGUAGES),
                "num_labels": self.roberta_hate_speech.num_labels,
                "label_mapping": self.roberta_hate_speech.id2label,
                "is_loaded": self.roberta_hate_speech.is_loaded,
                "status": self.roberta_hate_speech.status,
                "loading_time_s": getattr(self.roberta_hate_speech, "loading_time_s", None),
                "device": getattr(self.roberta_hate_speech, "device", None),
                "note": "English content-safety classifier. Strictly separate from claim truth verification.",
            },
        }

    def run_dual_inference(
        self,
        claim: str,
        evidence: List[EvidenceItem],
        language: Optional[str] = None,
    ) -> Tuple[Dict[str, ModelInferenceResult], ComparisonStatus]:
        """Execute inference on configured models and evaluate comparison completeness.

        Scientific & Reliability Rules:
        - Preserve both XLM-RoBERTa repositories as separate classification configurations.
        - The two XLM-RoBERTa checkpoints share 'xlm-roberta-base' and are NOT independent architectures.
        - Do not treat the RoBERTa hate-speech classifier as a fact-checking classifier.
        - Do not combine incompatible classification labels or claim that both models
          independently verify truth.
        - A future scientifically valid dual-model fact-checking comparison requires
          compatible fact-checking outputs; simply renaming RemBERT to RoBERTa does not
          satisfy cross-model fact-checking verification.
        - Keep model status as unavailable until actual weights load and real inference succeeds.
        - Explicitly handle unsupported languages for English-only models (RoBERTa).
        - Never generate fake predictions or confidence scores.
        """
        # Execute XLM-RoBERTa 7-class inference
        xlm_7class_result = self.xlm_roberta_7class.infer(claim, evidence, language=language)

        # Execute XLM-RoBERTa binary inference
        xlm_binary_result = self.xlm_roberta_binary.infer(claim, evidence, language=language)

        # Execute RoBERTa immigrant hate-speech inference (with explicit language handling)
        roberta_result = self.roberta_hate_speech.infer(claim, evidence, language=language)

        results: Dict[str, ModelInferenceResult] = {
            # Canonical key for backward-compatibility with UI and existing consumers
            "XLM-RoBERTa": xlm_7class_result,
            "XLM-RoBERTa-7Class": xlm_7class_result,
            "XLM-RoBERTa-Binary": xlm_binary_result,
            "RoBERTa": roberta_result,
        }

        # Track which models successfully executed with real loaded weights
        models_evaluated: List[str] = []
        if xlm_7class_result.is_available:
            models_evaluated.append("XLM-RoBERTa-7Class")
        if xlm_binary_result.is_available:
            models_evaluated.append("XLM-RoBERTa-Binary")
        if roberta_result.is_available:
            models_evaluated.append("RoBERTa")

        # Crucial Scientific Rule:
        # RoBERTa is a hate-speech classifier ('nusaiba19/roberta-immigrant-hate-speech'), NOT a fact-checking model.
        # Its outputs evaluate toxicity/bias against immigrants, not factual veracity.
        # Therefore, a fact-checking cross-model comparison CANNOT be considered complete
        # between XLM-RoBERTa and RoBERTa hate-speech, even if weights were loaded.
        is_complete = False

        if not models_evaluated:
            status_message = (
                "Comparison incomplete: RoBERTa (nusaiba19/roberta-immigrant-hate-speech) is a specialized "
                "immigrant hate-speech classifier and cannot serve as an independent fact-checking verifier. "
                "A scientifically valid dual-model fact-checking comparison requires compatible fact-checking outputs. "
                "Neither model weights are loaded."
            )
        else:
            status_message = (
                f"Comparison incomplete: Evaluated models: {', '.join(models_evaluated)}. "
                "RoBERTa (nusaiba19/roberta-immigrant-hate-speech) is an immigrant hate-speech classifier and "
                "cannot serve as an independent fact-checking verifier. XLM-RoBERTa checkpoints share the "
                "identical xlm-roberta-base foundation architecture and are not independent models. "
                "A scientifically valid dual-model fact-checking comparison requires independent compatible architectures."
            )

        comparison_status = ComparisonStatus(
            is_complete=is_complete,
            models_evaluated=models_evaluated,
            status_message=status_message,
        )

        return results, comparison_status

    # Alias for run_dual_inference
    run_inference = run_dual_inference
