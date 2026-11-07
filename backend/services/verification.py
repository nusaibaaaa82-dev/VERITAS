"""Verification Pipeline orchestrator for VERITAS.

Coordinates the end-to-end verification lifecycle:
Claim Submission
→ Language Identification (with explicit uncertainty handling)
→ Evidence Retrieval (strictly verified, no synthetic sources)
→ XLM-RoBERTa Inference (7-class & binary fact-checking adapters, no fake predictions)
→ RoBERTa Inference (immigrant hate-speech classifier, no fake predictions)
→ Evidence-Based Verdict Assessment (>= 2 independent verified sources required)
→ Structured Response

Strict Reliability Rules Enforced:
1. Never fabricate model predictions, confidence scores, evidence, or citations.
2. If language cannot be confirmed, return an explicit undetermined status ('und') rather than guessing English.
3. Preserve both XLM-RoBERTa repositories as separate classification configurations with exact label maps.
4. Do not claim the two XLM-RoBERTa checkpoints are independent transformer architectures (both share xlm-roberta-base).
5. Do NOT treat the RoBERTa hate-speech classifier as a fact-checking classifier.
6. Incompatible classification labels must never be combined to claim independent truth verification.
7. Preserve strict distinction between model prediction, evidence assessment, and final VERITAS verdict.
8. Do NOT map model predictions directly to final verdicts.
9. Explicitly handle unsupported languages for English-only models (RoBERTa).
10. A future scientifically valid dual-model fact-checking comparison requires compatible fact-checking outputs.
11. Model agreement is never treated as proof of truth.
12. If evidence is insufficient, verdict is strictly UNVERIFIED.
"""

from datetime import datetime, timezone
import hashlib
import re
import uuid
from typing import Optional, Set
from backend.models.model_manager import ModelManager
from backend.schemas.claim import (
    ClaimRequest,
    LanguageInfo,
    VerificationResultResponse,
)
from backend.services.claim_decomposition import ClaimDecompositionService
from backend.services.evidence_retrieval import EvidenceRetrievalService
from backend.services.proposition_matcher import PropositionMatcherService
from backend.services.verdict_engine import VerdictEngine


class VerificationPipeline:
    """End-to-end claim verification pipeline."""

    # High-frequency grammatical function words and core markers in English
    ENGLISH_FUNCTION_WORDS: Set[str] = {
        "the", "this", "that", "these", "those", "with", "have", "has", "had",
        "been", "from", "which", "their", "about", "between", "there", "would",
        "should", "could", "through", "is", "are", "was", "were", "and", "or",
        "in", "on", "at", "to", "for", "of", "by", "an", "not", "than",
        "global", "temperature", "temperatures", "increase", "increased",
        "climate", "warming", "vaccine", "vaccines", "reduce", "reduces",
        "risk", "severe", "disease", "diseases", "infectious", "carbon",
        "dioxide", "emissions", "rising", "cause", "causes", "caused",
    }

    # High-frequency grammatical function words, determiners, pronouns, and verbs in Spanish
    SPANISH_FUNCTION_WORDS: Set[str] = {
        # Articles & determiners
        "el", "la", "los", "las", "un", "una", "unos", "unas", "lo",
        "este", "esta", "estos", "estas", "esto", "ese", "esa", "esos", "esas", "eso",
        "aquel", "aquella", "aquellos", "aquellas", "aquello",
        "su", "sus", "mi", "mis", "tu", "tus", "nuestro", "nuestra", "nuestros", "nuestras",
        "otro", "otra", "otros", "otras", "todo", "toda", "todos", "todas", "cada",
        "mismo", "misma", "mismos", "mismas",
        # Prepositions, conjunctions, adverbs
        "a", "de", "del", "al", "en", "por", "con", "para", "como", "pero",
        "sobre", "entre", "hasta", "desde", "sin", "tras", "hacia", "contra",
        "segun", "según", "durante", "mediante", "que", "y", "e", "o", "u",
        "ni", "sino", "aunque", "porque", "pues", "si", "ya", "muy",
        "mas", "más", "menos", "tambien", "también", "tampoco",
        "donde", "dónde", "cuando", "cuándo", "quien", "quién", "quienes", "quiénes",
        # Pronouns
        "yo", "él", "ella", "ello", "ellos", "ellas", "nosotros", "nosotras",
        "usted", "ustedes", "me", "te", "se", "nos", "le", "les",
        # Copular & auxiliary verbs (ser, estar, haber, tener, poder, hacer)
        "es", "son", "era", "eran", "fue", "fueron", "ser", "sido", "siendo",
        "esta", "está", "estan", "están", "estaba", "estaban", "estuvo", "estar",
        "ha", "han", "hay", "habia", "había", "haber", "he", "hemos",
        "tiene", "tienen", "tenia", "tenía", "tener",
        "puede", "pueden", "podria", "podría", "podrian", "podrían", "poder",
        "hace", "hacen", "hizo", "hacer",
        # Common high-frequency verbs & stems
        "ayuda", "ayudan", "ayudar", "prevenir", "prevención",
        "aumenta", "aumentan", "aumentando", "aumentado",
        "disminuye", "disminuyen", "reduce", "reducen",
    }

    # Characteristic Spanish inflectional suffixes (requires stem length >= 3)
    SPANISH_INFLECTION_SUFFIXES = (
        "miento", "mientos",
        "acion", "ación", "aciones", "ciones",
        "dad", "dades",
        "ando", "iendo",
        "osa", "osas", "oso", "osos",
        "ivo", "iva", "ivos", "ivas",
        "ble", "bles",
    )

    # Specific non-Spanish French words to guard against cross-Romance false positives
    FRENCH_DISCRIMINATING_WORDS: Set[str] = {
        "est", "sont", "une", "du", "dans", "avec", "pour", "qui",
        "pas", "cette", "aussi", "sommes", "êtes", "étaient",
    }

    def __init__(
        self,
        evidence_service: Optional[EvidenceRetrievalService] = None,
        model_manager: Optional[ModelManager] = None,
        verdict_engine: Optional[VerdictEngine] = None,
        decomposition_service: Optional[ClaimDecompositionService] = None,
        proposition_matcher: Optional[PropositionMatcherService] = None,
    ):
        self.evidence_service = evidence_service or EvidenceRetrievalService()
        self.model_manager = model_manager or ModelManager()
        self.verdict_engine = verdict_engine or VerdictEngine()
        self.decomposition_service = decomposition_service or ClaimDecompositionService()
        self.proposition_matcher = proposition_matcher or PropositionMatcherService()

    def identify_language(self, text: str, user_hint: Optional[str] = None) -> LanguageInfo:
        """Identify the primary language of the claim statement.

        Reliability Rule:
        - Do not claim that all Latin-script text is English.
        - If language cannot be reliably confirmed, return explicit undetermined ('und') status.
        """
        # 1. User-supplied hint evaluation
        if user_hint and len(user_hint.strip()) in (2, 3):
            hint_clean = user_hint.strip().lower()
            return LanguageInfo(
                code=hint_clean,
                name=f"User-specified ({hint_clean.upper()})",
                is_reliable=True,
                method="user_hint",
                note="Language specified in claim request.",
            )

        # 2. Script-based analysis for non-Latin writing systems
        for char in text:
            cp = ord(char)
            # Cyrillic script
            if 0x0400 <= cp <= 0x04FF:
                return LanguageInfo(
                    code="ru",
                    name="Cyrillic Script (Russian / Slavic)",
                    is_reliable=True,
                    method="script_analysis",
                    note="Identified by Unicode Cyrillic character range.",
                )
            # Arabic script
            if 0x0600 <= cp <= 0x06FF:
                return LanguageInfo(
                    code="ar",
                    name="Arabic Script",
                    is_reliable=True,
                    method="script_analysis",
                    note="Identified by Unicode Arabic character range.",
                )
            # CJK Unified Ideographs (Chinese, Japanese Kanji, Korean Hanja)
            if 0x4E00 <= cp <= 0x9FFF:
                return LanguageInfo(
                    code="zh",
                    name="CJK Ideographs (Chinese / East Asian)",
                    is_reliable=True,
                    method="script_analysis",
                    note="Identified by Unicode CJK Unified Ideographs range.",
                )
            # Devanagari script (Hindi, Marathi, Sanskrit)
            if 0x0900 <= cp <= 0x097F:
                return LanguageInfo(
                    code="hi",
                    name="Devanagari Script (Hindi / Sanskrit)",
                    is_reliable=True,
                    method="script_analysis",
                    note="Identified by Unicode Devanagari character range.",
                )
            # Bengali script
            if 0x0980 <= cp <= 0x09FF:
                return LanguageInfo(
                    code="bn",
                    name="Bengali Script",
                    is_reliable=True,
                    method="script_analysis",
                    note="Identified by Unicode Bengali character range.",
                )
            # Greek script
            if 0x0370 <= cp <= 0x03FF:
                return LanguageInfo(
                    code="el",
                    name="Greek Script",
                    is_reliable=True,
                    method="script_analysis",
                    note="Identified by Unicode Greek character range.",
                )
            # Hebrew script
            if 0x0590 <= cp <= 0x05FF:
                return LanguageInfo(
                    code="he",
                    name="Hebrew Script",
                    is_reliable=True,
                    method="script_analysis",
                    note="Identified by Unicode Hebrew character range.",
                )

        # 3. Latin script analysis:
        # Extract Latin words including Spanish diacritical characters
        words = re.findall(r"\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]+\b", text.lower())
        if words:
            has_unique_spanish_chars = any(c in text.lower() for c in ("ñ", "¿", "¡"))
            has_spanish_accents = any(c in text.lower() for c in ("á", "é", "í", "ó", "ú"))
            has_french_specific_chars = any(c in text.lower() for c in ("è", "ê", "ë", "ç", "ô", "û", "œ", "æ"))

            english_matches = sum(1 for w in words if w in self.ENGLISH_FUNCTION_WORDS)
            spanish_matches = sum(1 for w in words if w in self.SPANISH_FUNCTION_WORDS)

            spanish_suffix_matches = sum(
                1 for w in words
                if len(w) >= 5 and any(w.endswith(sfx) and len(w) - len(sfx) >= 3 for sfx in self.SPANISH_INFLECTION_SUFFIXES)
                and w not in self.SPANISH_FUNCTION_WORDS
            )

            total_spanish_signals = spanish_matches + spanish_suffix_matches

            # French interference guard: prevent acute-accented or Romance French from false-matching as Spanish
            french_word_hits = sum(1 for w in words if w in self.FRENCH_DISCRIMINATING_WORDS)
            is_french = (
                has_french_specific_chars
                or french_word_hits >= 1
            ) and not has_unique_spanish_chars

            # 1. English dominance check
            if not is_french and english_matches >= 2 and english_matches > total_spanish_signals:
                return LanguageInfo(
                    code="en",
                    name="English",
                    is_reliable=True,
                    method="lexical_analysis",
                    note="Confirmed using distinctive English functional vocabulary markers.",
                )

            # 2. Spanish language detection with multiple corroborated signals
            if not is_french:
                # Signal A: Spanish-unique orthographic characters (ñ, ¿, ¡)
                if has_unique_spanish_chars and (total_spanish_signals >= 1 or len(words) <= 5):
                    return LanguageInfo(
                        code="es",
                        name="Spanish",
                        is_reliable=True,
                        method="lexical_analysis",
                        note="Confirmed by unique Spanish orthographic characters (ñ, ¿, ¡) and corroborating vocabulary.",
                    )

                # Signal B: Multiple distinctive Spanish vocabulary matches
                if spanish_matches >= 2:
                    return LanguageInfo(
                        code="es",
                        name="Spanish",
                        is_reliable=True,
                        method="lexical_analysis",
                        note="Confirmed using multiple distinctive Spanish grammatical and lexical markers.",
                    )

                # Signal C: Vocabulary match combined with morphological suffix
                if spanish_matches >= 1 and spanish_suffix_matches >= 1:
                    return LanguageInfo(
                        code="es",
                        name="Spanish",
                        is_reliable=True,
                        method="morphological_analysis",
                        note="Confirmed by Spanish vocabulary word and characteristic inflectional morphology.",
                    )

                # Signal D: Accented Spanish vowels accompanied by vocabulary or inflection
                if has_spanish_accents and (spanish_matches >= 1 or spanish_suffix_matches >= 1):
                    return LanguageInfo(
                        code="es",
                        name="Spanish",
                        is_reliable=True,
                        method="orthographic_and_lexical",
                        note="Confirmed by Spanish diacritical accents combined with lexical/morphological signals.",
                    )

                # Signal E: Short Spanish phrases with a strong distinctive Spanish word
                if len(words) <= 4 and spanish_matches >= 1 and english_matches == 0:
                    return LanguageInfo(
                        code="es",
                        name="Spanish",
                        is_reliable=True,
                        method="lexical_analysis",
                        note="Confirmed short Spanish phrase with distinctive grammatical marker.",
                    )

            # 3. English fallback for phrases with English markers
            if english_matches >= 2 or (len(words) <= 4 and english_matches >= 1 and total_spanish_signals == 0):
                return LanguageInfo(
                    code="en",
                    name="English",
                    is_reliable=True,
                    method="lexical_analysis",
                    note="Confirmed using distinctive English functional vocabulary markers.",
                )

        # 4. Explicit undetermined fallback for non-English/non-Spanish Latin or ambiguous text
        return LanguageInfo(
            code="und",
            name="Undetermined (Latin Script)",
            is_reliable=False,
            method="undetermined",
            note=(
                "Statement uses Latin script, but lacks distinctive English or Spanish grammatical markers. "
                "Returned undetermined ('und') and reported limitation honestly rather than guessing."
            ),
        )

    def verify_claim(self, request: ClaimRequest) -> VerificationResultResponse:
        """Execute the structured 6-step claim verification pipeline.

        Pipeline Steps:
        1. Claim Normalization: Clean input string and generate deterministic claim ID.
        2. Language Identification: Detect text language or return explicit undetermined code.
        3. Evidence Retrieval: Query verified primary source depositories (returns empty if disconnected).
        4. Model Inference (XLM-RoBERTa): Run 7-class & binary fact-checking adapters (is_available=False if not loaded).
        5. Model Inference (RoBERTa): Run immigrant hate-speech classifier (is_available=False if not loaded; not fact-checking).
        6. Verdict Synthesis: Formulate evidence-anchored verdict (UNVERIFIED if < 2 independent verified sources).
        7. Structured Response Assembly.
        """
        claim_text = request.claim.strip()

        # Step 1: Deterministic tracking ID
        content_hash = hashlib.sha256(claim_text.encode("utf-8")).hexdigest()[:12]
        claim_id = f"claim-{content_hash}-{uuid.uuid4().hex[:6]}"

        # Step 2: Language Identification (with explicit uncertainty handling)
        lang_info = self.identify_language(claim_text, request.language)

        # Step 3: Claim Decomposition into Factual Propositions
        raw_decomposition = self.decomposition_service.decompose_claim(
            claim=claim_text,
            claim_id=claim_id,
        )

        # Step 4: Evidence Retrieval (Strictly verified, never invented)
        retrieved_evidence = self.evidence_service.retrieve_evidence(
            claim=claim_text,
            language=lang_info.code,
        )
        retrieval_status = self.evidence_service.get_retrieval_status()

        # Step 5: Evidence-to-Proposition Matching & Coverage Calculation
        matched_decomposition = self.proposition_matcher.match_propositions(
            decomposition=raw_decomposition,
            evidence_items=retrieved_evidence,
        )

        # Step 6 & 7: Model Inference (XLM-RoBERTa [7-class & binary] + RoBERTa [hate-speech])
        model_results, comparison_status = self.model_manager.run_dual_inference(
            claim=claim_text,
            evidence=retrieved_evidence,
            language=lang_info.code,
        )

        # Step 8: Evidence-Based Verdict Assessment (Safety rule: multi-proposition coverage enforced)
        verdict_assessment = self.verdict_engine.assess_verdict(
            claim=claim_text,
            evidence=retrieved_evidence,
            model_results=model_results,
            comparison_status=comparison_status,
            decomposition=matched_decomposition,
        )

        # Step 9: Structured Response Assembly
        return VerificationResultResponse(
            claim_id=claim_id,
            claim=claim_text,
            language=lang_info.code,
            language_info=lang_info,
            comparison_status=comparison_status,
            models=model_results,
            evidence=retrieved_evidence,
            evidence_retrieval_status=str(retrieval_status.get("backend", "disconnected")),
            decomposition=matched_decomposition,
            verdict_assessment=verdict_assessment,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
