"""Evidence Relevance and Stance Assessment Engine for VERITAS.

Responsible for:
1. Evaluating whether retrieved evidence actually addresses the submitted claim.
2. Assessing directional stance (SUPPORTING, CONTRADICTING, NEUTRAL, UNKNOWN).
3. Enforcing strict scientific reliability standards:
   - Do NOT infer stance merely because the article discusses the same topic.
   - Never claim to have evaluated full text when only metadata or an abstract is present.
   - If relevance or stance cannot be established, retain NEUTRAL or UNKNOWN.
   - Provide transparent, traceable justifications for every relevance and stance determination.
"""

import re
from typing import Dict, List, Optional, Set
from backend.schemas.claim import EvidenceItem


# Multilingual grammatical stopwords (English, Spanish, Hindi, Bengali)
# Filtered out during lexical overlap computation to isolate substantive content terms
STOPWORDS: Set[str] = {
    # English
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any",
    "are", "aren't", "around", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "can't", "cannot", "could", "couldn't", "did",
    "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each", "few",
    "for", "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having",
    "he", "her", "here", "hers", "herself", "him", "himself", "his", "how", "i", "if",
    "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me", "more",
    "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on", "once",
    "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own",
    "same", "shan't", "she", "should", "shouldn't", "so", "some", "such", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "wasn't", "we", "were", "weren't", "what", "when", "where", "which", "while", "who",
    "whom", "why", "with", "won't", "would", "wouldn't", "you", "your", "yours", "yourself",
    # Spanish
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "en", "para", "por",
    "con", "sobre", "que", "como", "y", "o", "es", "son", "era", "eran", "fue", "fueron",
    "ha", "han", "hay", "su", "sus", "este", "esta", "estos", "estas", "pero", "mas",
    "al", "se", "lo", "le", "les", "ya", "muy", "sin", "entre", "hacia", "desde",
    # Hindi
    "है", "हैं", "हो", "था", "थे", "थी", "का", "के", "की", "में", "पर", "से", "को", "ने",
    "और", "या", "तो", "भी", "ही", "एक", "यह", "वह", "इस", "उस", "इन", "उन", "जो",
    "कर", "रहा", "रहे", "रही", "गया", "गए", "गई", "लिए", "हुए", "हुआ", "हुई",
    "सकता", "सकते", "सकती", "दिया", "दिए", "दी", "करने", "होने", "जाता", "जाते",
    # Bengali
    "এবং", "বা", "কিন্তু", "হয়", "হলো", "হচ্ছে", "ছিল", "হবে", "এর", "তে", "কে", "থেকে",
    "দ্বারা", "দিয়ে", "উপর", "মধ্যে", "একটি", "এই", "সেই", "যা", "করে", "করছে", "হয়ে",
    "আছে", "নেই", "পারে", "পারেন", "দেয়", "দেওয়া", "জন্য", "হতে", "যায়", "গেছে",
}

# Cross-lingual concept equivalents mapping non-English terms to English scientific literature descriptors
CONCEPT_EQUIVALENTS: Dict[str, Set[str]] = {
    # English Morphological Inflections
    "temperature": {"temperatures", "thermal", "warming"},
    "temperatures": {"temperature", "thermal", "warming"},
    "climate": {"climatic"},
    "climatic": {"climate"},
    "warming": {"temperature", "warmth", "heating"},
    "vaccine": {"vaccines", "vaccination", "immunization"},
    "vaccines": {"vaccine", "vaccination", "immunization"},
    "vaccination": {"vaccines", "vaccine", "immunization"},
    "disease": {"diseases", "illness", "infection"},
    "diseases": {"disease", "illnesses", "infections"},
    "infection": {"infections", "infectious"},
    "infections": {"infection", "infectious"},
    "infectious": {"infection", "infections"},
    "immigrant": {"immigrants", "migrant", "migration", "alien", "aliens", "noncitizen", "noncitizens"},
    "immigrants": {"immigrant", "migrants", "migration", "alien", "aliens", "noncitizen", "noncitizens"},
    "migrant": {"migrants", "immigrant"},
    "migrants": {"migrant", "immigrants"},
    "emission": {"emissions"},
    "emissions": {"emission"},
    "glacier": {"glaciers"},
    "glaciers": {"glacier"},

    # Climate & Temperature (HI / BN / ES <-> EN)
    "तापमान": {"temperature", "temperatures", "thermal", "warming", "temperatura", "temperaturas"},
    "वैश्विक": {"global", "worldwide", "planetary"},
    "वृद्धि": {"increase", "increased", "increasing", "warming", "rise", "rising", "trend", "aumento"},
    "बढ़": {"increase", "increased", "rising", "rise"},
    "जलवायु": {"climate", "climatic", "clima", "climático"},
    "ग्लोबल": {"global", "worldwide"},
    "वार्मिंग": {"warming", "warmth", "heating"},
    "पर्यावरण": {"environment", "environmental", "medioambiente"},
    "मौसम": {"weather", "meteorology", "clima"},
    "उत्सर्जन": {"emissions", "emission"},
    "समुद्र": {"sea", "ocean", "marine", "oceans"},
    "तापমাত্রা": {"temperature", "temperatures", "thermal", "warming"},
    "জলবায়ু": {"climate", "climatic"},
    "উষ্ণায়ন": {"warming", "warmth", "heating"},
    "আবহাওয়া": {"weather", "meteorology"},
    "পরিবেশ": {"environment", "environmental"},
    "সমুদ্রপৃষ্ঠ": {"sea level", "ocean"},
    "calentamiento": {"warming", "heating", "global warming", "উষ্ণায়ন", "वार्मिंग"},
    "temperatura": {"temperature", "temperatures", "thermal", "तापमान", "तापমাত্রা"},
    "temperaturas": {"temperature", "temperatures", "thermal", "तापमान", "तापমাত্রা"},
    "clima": {"climate", "climatic", "जलवायु", "জলবায়ু"},
    "climático": {"climate", "climatic", "atmospheric"},
    "climática": {"climate", "climatic", "atmospheric"},
    "planeta": {"planet", "earth", "global"},
    "océano": {"ocean", "sea", "marine"},
    "océanos": {"oceans", "seas", "marine"},
    "emisiones": {"emissions", "carbon"},
    "aumento": {"increase", "rise", "rising", "वृद्धि"},

    # Health & Vaccines (HI / BN / ES <-> EN)
    "टीका": {"vaccine", "vaccines", "vaccination", "immunization", "vacuna", "vacunas", "টিকা"},
    "टीके": {"vaccine", "vaccines", "vaccination", "immunization", "vacuna", "vacunas", "টিকা"},
    "टीकाकरण": {"vaccination", "immunization"},
    "संक्रामक": {"infectious", "infection", "contagious", "infecciosa", "infecciosas", "সংক্রামক"},
    "संक्रमण": {"infection", "infections", "transmission", "সংক্রমণ"},
    "बीमारी": {"disease", "diseases", "illness", "enfermedad", "enfermedades", "রোগ"},
    "बीमारियों": {"disease", "diseases", "illness", "enfermedad", "enfermedades", "রোগ"},
    "रोग": {"disease", "diseases", "disorder", "illness", "enfermedad", "enfermedades"},
    "स्वास्थ्य": {"health", "healthcare", "salud"},
    "दवा": {"medicine", "drug", "pharmaceutical", "চিকিৎসা", "ওষুধ"},
    "दवाएं": {"medicines", "drugs", "pharmaceuticals"},
    "इलाज": {"treatment", "cure", "therapy"},
    "वायरस": {"virus", "viral"},
    "बचाव": {"prevention", "protection", "prevent", "protect"},
    "मदद": {"help", "reduce", "aid"},
    "টিকা": {"vaccine", "vaccines", "vaccination", "immunization", "vacuna", "vacunas", "टीका", "टीके"},
    "টিকাদান": {"vaccination", "immunization"},
    "সংক্রামক": {"infectious", "infection", "contagious", "infecciosa", "infecciosas", "संक्रामक"},
    "সংক্রমণ": {"infection", "infections", "transmission"},
    "রোগ": {"disease", "diseases", "illness", "disorder", "enfermedad", "बीमारी"},
    "অসুখ": {"illness", "disease"},
    "চিকিৎসা": {"treatment", "medical", "therapy"},
    "ওষুধ": {"medicine", "drug"},
    "ঔষধ": {"medicine", "pharmaceutical"},
    "প্রতিরোধ": {"prevention", "prevent", "protection", "prophylaxis", "prevención", "बचाव"},
    "কার্যকর": {"effective", "efficacy", "beneficial"},
    "ভূমিকা": {"role", "effect"},
    "জীবাণু": {"pathogen", "germ", "microbe", "bacteria"},
    "ভাইরাস": {"virus", "viral"},
    "vacuna": {"vaccine", "vaccines", "vaccination", "immunization", "टीका", "টিকা"},
    "vacunas": {"vaccine", "vaccines", "vaccination", "immunization", "टीके", "টিকা"},
    "vacunación": {"vaccination", "immunization"},
    "enfermedades": {"diseases", "disease", "illness", "infections", "बीमारियों", "রোগ"},
    "enfermedad": {"disease", "illness", "disorder", "बीमारी", "রোগ"},
    "infecciosas": {"infectious", "infection", "contagious", "संक्रामक", "সংক্রামক"},
    "infecciosa": {"infectious", "infection", "contagious", "संक्रामक", "সংক্রামক"},
    "prevenir": {"prevent", "prevention", "prophylaxis", "बचाव", "প্রতিরোধ"},
    "prevención": {"prevention", "prophylaxis", "protective", "बचाव", "প্রতিরোধ"},
    "reducen": {"reduce", "decreases", "lower"},
    "mortalidad": {"mortality", "death", "fatalities"},
    "salud": {"health", "healthcare"},

    # Immigration (HI / BN / ES <-> EN)
    "inmigrantes": {"immigrants", "immigrant", "migrants", "migration"},
    "inmigrante": {"immigrant", "migrant"},
    "migrantes": {"migrants", "immigrants", "migration"},
    "migrante": {"migrant", "immigrant"},
    "impuestos": {"taxes", "tax", "taxation"},
    "delincuencia": {"crime", "criminality", "offenses"},
    "frontera": {"border", "borders", "frontier"},
    "refugiados": {"refugees", "refugee", "asylum"},
    "economía": {"economy", "economic", "contribution"},
    "trabajadores": {"workers", "laborers", "workforce"},
    "delito": {"crime", "offense"},
    "prisión": {"prison", "incarceration"},
    "encarcelamiento": {"incarceration", "imprisonment"},
    "प्रवासी": {"immigrant", "immigrants", "migrant", "migrants", "migration"},
    "कामगार": {"workers", "labor", "workforce"},
    "अपराध": {"crime", "criminal", "offenses"},
    "अर्थव्यवस्था": {"economy", "economic"},
    "योगदान": {"contribution", "contribute"},
    "हिंसा": {"violence", "violent"},
    "अभ्रवासी": {"immigrant", "immigrants"},
    "অভিবাসী": {"immigrant", "immigrants", "migrant", "migrants"},
    "প্রবাসী": {"expatriate", "migrant", "remittance", "workers"},
    "শ্রমিক": {"workers", "laborers", "workforce"},
    "রেমিট্যান্স": {"remittance", "remittances", "earnings"},
    "অর্থনীতি": {"economy", "economic"},
    "নিরাপত্তা": {"security", "safety"},
    "হুমকি": {"threat", "risk"},

    # Employment Rights & Labor Standards (HI / BN / ES <-> EN)
    "wage": {"wages", "salary", "pay", "compensation", "earnings", "flsa"},
    "wages": {"wage", "salary", "pay", "compensation", "earnings", "flsa"},
    "overtime": {"overtime pay", "hours", "compensation"},
    "workplace": {"employment", "job", "work", "employer", "labor"},
    "theft": {"wage theft", "unpaid", "stolen", "underpayment", "back wages"},
    "salario": {"wage", "wages", "salary", "sueldo"},
    "salarios": {"wage", "wages", "salary", "sueldo"},
    "sueldo": {"salary", "wage", "wages"},
    "trabajador": {"worker", "employee", "laborer"},
    "trabajadores": {"workers", "employees", "laborers"},
    "laboral": {"labor", "employment", "workplace"},
    "robo": {"theft", "wage theft", "stolen"},
    "denunciar": {"report", "reporting", "file", "filed", "complaint"},
    "denuncia": {"complaint", "report", "reporting", "file", "filed"},
    "indocumentados": {"undocumented", "immigrant", "immigrants"},
    "indocumentado": {"undocumented", "immigrant", "immigrants"},
    "मजदूरी": {"wage", "wages", "salary", "pay", "compensation"},
    "वेतन": {"salary", "wage", "wages", "pay"},
    "कार्यस्थल": {"workplace", "employment", "job"},
    "श्रमिक": {"worker", "workers", "labor", "laborer", "employee", "employees"},
    "मजदूर": {"worker", "workers", "laborer", "employee"},
    "रिपोर्ट": {"report", "reporting", "file", "filed", "complaint"},
    "शिकायत": {"complaint", "report", "reporting", "file", "filed"},
    "चोरी": {"theft", "wage theft", "stolen"},
    "मजুরি": {"wage", "wages", "salary", "pay"},
    "বেতন": {"salary", "wage", "wages", "pay"},
    "কর্মক্ষেত্র": {"workplace", "employment", "job"},
    "কর্মক্ষেত্রে": {"workplace", "employment", "job"},
    "শ্রমিক": {"worker", "workers", "laborer", "employee", "employees"},
    "শ্রমিকরা": {"worker", "workers", "laborer", "employee", "employees"},
    "অভিযোগ": {"complaint", "report", "reporting", "file", "filed"},
    "চুরি": {"theft", "wage theft", "stolen"},
    "চুরির": {"theft", "wage theft", "stolen"},
    "report": {"reporting", "reports", "reported", "file", "filed", "filing", "complaint", "complaints", "whistleblower", "instituted", "denuncia", "denunciar", "शिकायत", "অভিযোগ"},
    "reporting": {"report", "reports", "file", "filed", "filing", "complaint", "whistleblower"},
    "employee": {"worker", "workers", "employees", "laborer", "person"},
    "worker": {"employee", "employees", "workers", "laborer"},
    "workers": {"employee", "employees", "worker", "laborers"},
    "retaliation": {"discharge", "discriminate", "threats", "adverse action", "reprisal"},

    # General Science (HI / BN / ES <-> EN)
    "fotosíntesis": {"photosynthesis", "chlorophyll"},
    "oxígeno": {"oxygen", "atmosphere"},
    "gravedad": {"gravity", "gravitational"},
    "plana": {"flat", "plane"},
    "solar": {"solar", "sun", "sunlight"},
    "órbita": {"orbit", "orbits", "planetary"},
    "minutos": {"minutes", "time"},
    "luz": {"light", "sunlight", "radiation"},
    "प्रकाश": {"light", "sunlight"},
    "सूर्य": {"sun", "solar"},
    "परिक्रमा": {"orbit", "orbits", "revolve"},
    "चंद्रमा": {"moon", "lunar"},
    "उपग्रह": {"satellite", "moon"},
    "उबलता": {"boil", "boiling", "temperature"},
    "সালোকসংশ্লেষণ": {"photosynthesis"},
    "সূর্যালোক": {"sunlight", "solar"},
    "অক্সিজেন": {"oxygen"},
    "সমতল": {"flat", "plane"},
    "পৃথিবী": {"earth", "planet", "terrestrial"},
    "esferoide": {"spheroid", "curvature", "geodesy"},
    "oblato": {"oblate", "spheroid"},
    "planetas": {"planets", "planetary", "orbit"},
    "planeta": {"planet", "planetary"},
    "गोलाकार": {"spherical", "sphere", "spheroid", "curvature"},
    "गुरुत्वाकर्षण": {"gravity", "gravitation", "gravitational"},
    "ग्रह": {"planet", "planetary"},
    "গোলক": {"sphere", "spherical", "spheroid", "curvature"},
    "মহাকর্ষ": {"gravity", "gravitation", "gravitational"},
    "সূর্যের": {"sun", "solar"},
    "চারদিকে": {"orbit", "orbits", "revolve"},
    "আবর্তিত": {"orbit", "orbits", "planetary"},

    # Statutory & Legal Labor / Employment Terminology (FLSA & Immigration Law)
    "undocumented": {"unauthorized", "indocumentado", "indocumentados", "noncitizen", "noncitizens"},
    "unauthorized": {"undocumented", "alien", "aliens", "noncitizen"},
    "alien": {"aliens", "immigrant", "immigrants", "noncitizen", "noncitizens"},
    "aliens": {"alien", "immigrant", "immigrants", "noncitizen", "noncitizens"},
    "noncitizen": {"noncitizens", "immigrant", "immigrants", "alien", "aliens", "undocumented"},
    "noncitizens": {"noncitizen", "immigrant", "immigrants", "alien", "aliens", "undocumented"},
    "wage": {"wages", "minimum", "206", "206a", "statutory", "damages", "compensation", "earnings", "pay", "sueldo", "salario"},
    "wages": {"wage", "minimum", "206", "206a", "statutory", "damages", "compensation", "earnings", "pay", "sueldo", "salario"},
    "minimum": {"statutory", "mandated", "206", "206a"},
    "workers": {"worker", "work", "employee", "employees", "laborer", "laborers", "workforce", "trabajadores"},
    "worker": {"workers", "work", "employee", "employees", "laborer", "laborers", "workforce", "trabajador"},
    "206": {"wage", "wages", "minimum", "flsa"},
    "206a": {"wage", "wages", "minimum", "flsa"},
    "207": {"overtime", "flsa", "wage", "wages"},
    "207a": {"overtime", "flsa", "wage", "wages"},
    "216": {"damages", "flsa", "statutory", "penalties", "remedies"},
    "216b": {"damages", "flsa", "statutory", "penalties", "remedies"},
    "flsa": {"fair", "labor", "standards", "act", "wage", "wages", "206", "206a", "207", "207a", "216", "216b"},
    "standards": {"standard", "flsa"},
    "entitled": {"eligible", "right", "rights", "authorized"},
}

# Generic statistical, temporal, and non-topical modifiers that do not establish domain relevance on their own
GENERIC_MODIFIERS: Set[str] = {
    # English
    "increased", "increase", "increasing", "significantly", "significant", "decreased", "decrease",
    "past", "recent", "years", "century", "study", "studies", "data", "analysis", "reported",
    "report", "shows", "shown", "show", "findings", "found", "rate", "high", "higher", "low",
    "levels", "level", "new", "results", "result", "evidence", "associated", "impact", "effect",
    "effects", "observed", "observation", "first", "second", "multiple", "various", "general",
    "global", "worldwide", "across", "world", "planetary", "earth", "planet", "terrestrial", "globe",
    # Spanish
    "aumento", "aumentado", "significativo", "pasado", "estudio", "datos", "análisis", "nuevo",
    "mundial", "general", "efecto", "efectos", "tasa", "tasas", "nivel", "niveles", "tierra", "planeta",
    # Hindi
    "वृद्धि", "लगातार", "अध्ययन", "रिपोर्ट", "अधिक", "कम", "वर्ष", "वैश्विक", "प्रभाव", "पृथ्वी", "ग्रह",
    # Bengali
    "বৃদ্ধি", "অধ্যয়ন", "রিপোর্ট", "বেশি", "কম", "বছর", "বৈশ্বিক", "প্রভাব", "পৃথিবী",
    "বৃদ্ধি", "অধ্যয়ন", "রিপোর্ট", "বেশি", "কম", "বছর", "বৈশ্বিক", "প্রভাব",
}

# Explicit directional / polarity markers for stance evaluation (Multilingual: EN, ES, HI, BN)
REFUTATION_MARKERS: List[str] = [
    # English
    "no evidence",
    "no link",
    "no correlation",
    "no causal connection",
    "refute",
    "refuted",
    "refutes",
    "debunk",
    "debunked",
    "debunks",
    "disproven",
    "disproved",
    "false",
    "untrue",
    "unsupported",
    "contrary to",
    "misconception",
    "myth",
    "hoax",
    "failed to replicate",
    "not visible",
    "cannot be seen",
    "not supported",
    "rejected the hypothesis",
    # Spanish
    "no hay evidencia",
    "no existe evidencia",
    "sin evidencia",
    "sin relación",
    "no demuestra",
    "falso",
    "falsa",
    "desmentido",
    "desmiente",
    "refutado",
    "refuta",
    "desvirtuado",
    "mito",
    "bulo",
    "inconsistente con",
    "rechaza la hipótesis",
    # Hindi
    "कोई सबूत नहीं",
    "सबूत नहीं मिला",
    "खारिज",
    "गलत",
    "झूठ",
    "दावा खारिज",
    "अस्वीकार",
    "भ्रम",
    "असत्य",
    "पुष्टि नहीं",
    "निराधार",
    # Bengali
    "কোন প্রমাণ নেই",
    "প্রমাণ মেলেনি",
    "ভুল",
    "মিথ্যা",
    "ভিত্তিহীন",
    "খারিজ",
    "অসত্য",
    "গুজব",
    "দাবি নাকচ",
    "প্রমাণিত নয়",
]

AFFIRMATION_MARKERS: List[str] = [
    # English
    "confirm",
    "confirms",
    "confirmed",
    "confirm that",
    "confirms that",
    "corroborates",
    "corroborated",
    "demonstrates",
    "demonstrate",
    "evidence shows",
    "measurements show",
    "observations confirm",
    "consistent with",
    "substantiates",
    "increased significantly",
    "ongoing increase",
    "rising trend",
    "record high",
    "establish that",
    "establishes that",
    "established that",
    "verified that",
    "proven",
    # Spanish
    "confirma",
    "confirmado",
    "demuestra",
    "demostrado",
    "evidencia muestra",
    "los datos confirman",
    "estudios confirman",
    "aumento significativo",
    "respalda",
    "corrobora",
    "comprobado",
    "protege contra",
    "reduce el riesgo",
    # Hindi
    "पुष्टि करता है",
    "पुष्टि की",
    "साबित हुआ",
    "वृद्धि हुई",
    "प्रमाणित",
    "दर्शाता है",
    "सबूत दिखाते हैं",
    "अध्ययन के अनुसार",
    "महत्वपूर्ण भूमिका",
    "बचाव करते हैं",
    "रोकथाम में मदद",
    "खतरा कम",
    # Bengali
    "নিশ্চিত করে",
    "নিশ্চিত করেছে",
    "প্রমাণিত",
    "বৃদ্ধি পেয়েছে",
    "গবেষণায় দেখা গেছে",
    "তথ্য নিশ্চিত",
    "কার্যকর ভূমিকা",
    "সুরক্ষা প্রদান করে",
    "প্রতিরোধে সাহায্য করে",
    "ঝুঁকি কমায়",
]


class EvidenceRelevanceEngine:
    """Evaluates topical relevance and propositional stance of evidence items relative to a claim."""

    @staticmethod
    def extract_content_tokens(text: str) -> Set[str]:
        """Extract significant lowercased content tokens excluding stopwords, preserving Unicode scripts."""
        bad_chars = set("\"'*^()[]{}<>;:,.?!/@#$%&=+~|\\।॥§¶`“”’\n\r\t")
        raw_words = text.lower().split()
        tokens = set()
        for w in raw_words:
            clean = "".join(ch for ch in w if ch not in bad_chars).strip()
            if len(clean) >= 2 and clean not in STOPWORDS:
                tokens.add(clean)
        return tokens

    def assess_item(self, claim: str, item: EvidenceItem) -> EvidenceItem:
        """Evaluate and enrich an EvidenceItem with relevance status, score, stance, and justifications."""
        if not claim or not claim.strip():
            item.relevance_status = "UNDETERMINED"
            item.relevance_score = 0.0
            item.relevance_justification = "Claim statement was empty; relevance cannot be determined."
            item.stance = "UNKNOWN"
            item.stance_justification = "Claim statement was empty; stance cannot be determined."
            return item

        # Rule: If only citation metadata is available (no abstract or full text),
        # never infer stance from title/metadata alone.
        if item.text_availability == "METADATA_ONLY" or not item.snippet:
            item.relevance_status = "UNDETERMINED"
            item.relevance_score = 0.0
            item.relevance_justification = (
                "Citation metadata record only: full-text abstract or excerpt is unindexed. "
                "Per VERITAS scientific standards, substantive relevance cannot be verified from metadata alone."
            )
            item.stance = "NEUTRAL"
            item.stance_justification = (
                "Citation metadata record only. Without abstract or empirical text, "
                "evaluating directional stance is scientifically invalid; stance retained as NEUTRAL."
            )
            return item

        claim_tokens = self.extract_content_tokens(claim)
        snippet_tokens = self.extract_content_tokens(item.snippet)
        title_tokens = self.extract_content_tokens(item.title)
        combined_evidence_tokens = snippet_tokens.union(title_tokens)

        if not claim_tokens:
            item.relevance_status = "UNDETERMINED"
            item.relevance_score = 0.0
            item.relevance_justification = "Claim contained no distinct content words after stopword removal."
            item.stance = "NEUTRAL"
            item.stance_justification = "Retained as NEUTRAL due to undetermined claim terminology."
            return item

        # Expand claim tokens with cross-lingual concept equivalents for multilingual scientific matching
        expanded_claim_tokens = set(claim_tokens)
        cross_lingual_active = False
        for tok in claim_tokens:
            if tok in CONCEPT_EQUIVALENTS:
                expanded_claim_tokens.update(CONCEPT_EQUIVALENTS[tok])
                cross_lingual_active = True

        # Compute lexical overlap against native tokens first, then expanded cross-lingual tokens
        native_overlap = claim_tokens.intersection(combined_evidence_tokens)
        expanded_overlap = expanded_claim_tokens.intersection(combined_evidence_tokens)

        # Use expanded overlap if cross-lingual mapping matched, otherwise native overlap
        overlap = expanded_overlap if len(expanded_overlap) > len(native_overlap) else native_overlap
        is_cross_lingual_match = cross_lingual_active and len(expanded_overlap) > len(native_overlap)

        overlap_score = len(overlap) / max(1, len(claim_tokens))
        overlap_score_rounded = round(min(1.0, overlap_score), 3)

        snippet_lower = item.snippet.lower()
        claim_lower = claim.lower()

        # Step 1: Relevance Decision
        # Require substantive domain entity overlap (not purely generic modifiers like 'increased significantly')
        substantive_overlap = overlap - GENERIC_MODIFIERS
        has_substantive_entity = len(substantive_overlap) >= 1

        # Require >= 25% overlap of substantive claim terms or at least 2 distinct key concept words,
        # AND at least one non-generic domain entity
        is_relevant = ((overlap_score >= 0.25) or (len(overlap) >= 2)) and has_substantive_entity

        if not is_relevant:
            missing_tokens = list(claim_tokens - overlap)[:4]
            item.relevance_status = "IRRELEVANT"
            item.relevance_score = overlap_score_rounded
            if not has_substantive_entity and len(overlap) > 0:
                item.relevance_justification = (
                    f"Off-topic entity mismatch. Overlap {list(overlap)} consists solely of generic modifiers "
                    f"without core topic entities."
                )
            else:
                item.relevance_justification = (
                    f"Off-topic or insufficient entity overlap ({overlap_score_rounded:.0%}). "
                    f"Core claim terms {missing_tokens} are absent from evidence excerpt."
                )
            item.stance = "NEUTRAL"
            item.stance_justification = (
                "Evidence text is off-topic relative to the claim proposition. "
                "Stance is strictly NEUTRAL and does not evaluate claim truth."
            )
            return item

        # Item is RELEVANT
        item.relevance_status = "RELEVANT"
        item.relevance_score = overlap_score_rounded
        overlap_sample = list(overlap)[:5]
        if is_cross_lingual_match:
            item.relevance_justification = (
                f"Thematic alignment confirmed via cross-lingual concept mapping ({overlap_score_rounded:.0%}). "
                f"Matched scientific concepts: {overlap_sample}."
            )
        else:
            item.relevance_justification = (
                f"Thematic alignment confirmed ({overlap_score_rounded:.0%}). "
                f"Shared core concepts: {overlap_sample}."
            )

        # Step 1b: Domain Mismatch Filtering
        # Prevent off-domain contamination (e.g. cellular migration for human immigration, or rainfall for planetary geodesy)
        # 1. Biological / cellular migration retrieved for human immigration claims
        if any(tok in claim_lower for tok in ("immigrant", "immigrants", "immigration", "migrant", "inmigrante", "inmigrantes", "प्रवासी", "অভিবাসী")):
            if any(bio in snippet_lower or bio in (item.title or "").lower() for bio in ("cell migration", "cellular migration", "bird migration", "avian migration", "cell motility", "metastasis", "cancer")):
                item.relevance_status = "IRRELEVANT"
                item.relevance_score = 0.0
                item.relevance_justification = "Domain mismatch: biological, cellular, or avian migration literature retrieved for human immigration / demographic claim."
                item.stance = "NEUTRAL"
                item.stance_justification = "Off-topic biological mechanism; does not evaluate human demographic proposition."
                return item

        # 1b. Extraterrestrial / astronomical / planetary literature retrieved for human immigration / labor claims
        if any(tok in claim_lower for tok in ("immigrant", "immigrants", "immigration", "migrant", "undocumented", "unauthorized", "inmigrante", "inmigrantes", "wage", "wages", "labor", "worker", "workers")):
            if any(astro in snippet_lower or astro in (item.title or "").lower() for astro in (
                "extraterrestrial", "seti", "astronomy", "astrophysics", "biosignature", "biosignatures",
                "technosignature", "technosignatures", "exoplanet", "exoplanets", "spacecraft",
                "interstellar", "galaxy", "galaxies", "astronomical", "ephemerides", "ephemeris", "radio telescope"
            )):
                if not any(lab in snippet_lower or lab in (item.title or "").lower() for lab in ("wage", "overtime", "flsa", "minimum wage", "unpaid wages", "wage theft", "workplace", "department of labor")):
                    item.relevance_status = "IRRELEVANT"
                    item.relevance_score = 0.0
                    item.relevance_justification = "Domain mismatch: astronomical, planetary, or extraterrestrial search literature retrieved for human immigration or labor claim."
                    item.stance = "NEUTRAL"
                    item.stance_justification = "Off-topic astronomical or astrobiological study; does not evaluate human legal rights or labor protections."
                    return item

        # 1c. Human immigration / labor records retrieved for extraterrestrial / astronomy claims
        if any(tok in claim_lower for tok in ("extraterrestrial", "seti", "alien life", "biosignature", "exoplanet", "astrobiology", "astronomy", "ufo", "uap")):
            if any(imm in snippet_lower or imm in (item.title or "").lower() for imm in (
                "undocumented", "department of labor", "flsa", "border patrol", "deportation", "visa", "green card", "uscis"
            )):
                item.relevance_status = "IRRELEVANT"
                item.relevance_score = 0.0
                item.relevance_justification = "Domain mismatch: human immigration or statutory labor document retrieved for astronomical or astrobiological claim."
                item.stance = "NEUTRAL"
                item.stance_justification = "Off-topic human legal/statutory document does not evaluate extraterrestrial proposition."
                return item

        # 2. Climate papers retrieved for planetary physics / geodesy claims
        if any(tok in claim_lower for tok in ("spheroid", "curvature", "geodesy", "geodetic", "orbit", "orbits", "gravity", "lunar", "retroreflector", "plana", "esferoide", "মহাকর্ষ", "গোলক")):
            if any(clim in snippet_lower or clim in (item.title or "").lower() for clim in ("calentamiento global", "global warming", "pluviométrico", "greenhouse gas", "emissions", "drought", "जलवाय", "জলবায়ু")) and not any(geo in snippet_lower or geo in (item.title or "").lower() for geo in ("spheroid", "curvature", "geodesy", "geodetic", "gravity", "gravitational", "orbit", "orbital", "lunar", "laser ranging", "oblato", "esferoide")):
                item.relevance_status = "IRRELEVANT"
                item.relevance_score = 0.0
                item.relevance_justification = "Domain mismatch: climatology / meteorological study retrieved for planetary geometry, geodesy, or celestial physics claim."
                item.stance = "NEUTRAL"
                item.stance_justification = "Off-topic climatological study; does not evaluate planetary curvature or orbital mechanics."
                return item

        # 3. Biomedical / vaccine papers retrieved for climate claims
        if any(tok in claim_lower for tok in ("climate", "warming", "temperature", "temperaturas", "calentamiento", "तापमान", "জলবায়ু")):
            if any(med in snippet_lower or med in (item.title or "").lower() for med in ("vaccin", "vacuna", "remdesivir", "immuniz", "टीका", "টিকা")):
                item.relevance_status = "IRRELEVANT"
                item.relevance_score = 0.0
                item.relevance_justification = "Domain mismatch: biomedical / pharmaceutical paper retrieved for atmospheric or climate claim."
                item.stance = "NEUTRAL"
                item.stance_justification = "Off-topic biomedical paper; does not evaluate climate proposition."
                return item

        # 4. Veterinary medicine retrieved for human immunization claims
        if any(tok in claim_lower for tok in ("vaccine", "vaccines", "vacuna", "vacunas", "टीके", "টিকা")):
            if any(vet in snippet_lower or vet in (item.title or "").lower() for vet in ("bovina", "bovine", "porcine", "equine", "canine")) and not any(hum in snippet_lower for hum in ("human", "pediatric", "child", "infant", "humano", "niño")):
                item.relevance_status = "IRRELEVANT"
                item.relevance_score = 0.0
                item.relevance_justification = "Domain mismatch: veterinary medicine study retrieved for human vaccination / health claim."
                item.stance = "NEUTRAL"
                item.stance_justification = "Off-topic veterinary paper; does not evaluate human public health proposition."
                return item

        # 5. Administrative / Procurement health records retrieved for medical efficacy claims
        if any(tok in claim_lower for tok in ("vaccine", "vaccines", "vacuna", "vacunas", "टीके", "টিকা", "disease", "enfermedad")):
            if any(adm in snippet_lower or adm in (item.title or "").lower() for adm in ("procurement plan", "budget estimates", "administrative arrangements", "financial audit", "audit report")) and not any(clin in snippet_lower for clin in ("efficac", "safe", "prevent", "protect", "reduc", "surveillan")):
                item.relevance_status = "IRRELEVANT"
                item.relevance_score = 0.1
                item.relevance_justification = "Administrative / procurement health document retrieved for medical efficacy claim lacking clinical or epidemiological findings."
                item.stance = "NEUTRAL"
                item.stance_justification = "Administrative document does not evaluate medical efficacy or health outcome proposition."
                return item

        # 6. Administrative Loan / Project Appraisal records retrieved for empirical physical or medical claims
        wb_admin_markers = (
            "loan agreement",
            "project appraisal document",
            "financing agreement",
            "procurement plan",
            "implementation completion report",
            "disbursement",
            "environmental and social commitment plan",
            "resettlement action plan",
        )
        if any(adm in snippet_lower or adm in (item.title or "").lower() for adm in wb_admin_markers):
            if any(tok in claim_lower for tok in (
                "vaccine", "vacuna", "टीके", "টিকা", "disease", "enfermedad", "efficac",
                "temperature", "emissions", "carbon", "warming", "spheroid", "curvature",
                "calentamiento", "तापमान", "জলবায়ু"
            )):
                if not any(emp in snippet_lower for emp in ("empirical evidence", "observed temperature", "clinical efficacy", "epidemiological")):
                    item.relevance_status = "IRRELEVANT"
                    item.relevance_score = 0.1
                    item.relevance_justification = (
                        "Administrative loan or infrastructure project appraisal document retrieved for "
                        "empirical or scientific claim lacking substantive scientific findings."
                    )
                    item.stance = "NEUTRAL"
                    item.stance_justification = (
                        "Institutional loan or project administration document does not evaluate "
                        "physical or biomedical proposition."
                    )
                    return item

        # 7. Employment Rights & Workplace Wage Theft Protection Filter
        is_employment_claim = any(
            emp in claim_lower for emp in (
                "wage", "wages", "wage theft", "workplace", "salary", "salaries", "overtime",
                "minimum wage", "unpaid wages", "worker", "workers", "employee", "employees",
                "labor law", "labor rights", "flsa", "salario", "sueldo", "robo de salario",
                "मजदूरी", "वेतन", "मजदूरी चोरी", "মজুরি", "বেতন", "মজুরি চুরি"
            )
        )
        if is_employment_claim:
            # A. Filter out biomedical / vaccine / medical literature
            if any(med in snippet_lower or med in (item.title or "").lower() for med in ("vaccin", "vacuna", "remdesivir", "immuniz", "covid", "pediatric", "hospitalized with", "टीका", "টিকা", "disease", "enfermedad")):
                if not any(lab in snippet_lower or lab in (item.title or "").lower() for lab in ("wage", "overtime", "flsa", "minimum wage", "labor", "workplace")):
                    item.relevance_status = "IRRELEVANT"
                    item.relevance_score = 0.0
                    item.relevance_justification = "Domain mismatch: biomedical / pharmaceutical paper retrieved for workplace employment rights claim."
                    item.stance = "NEUTRAL"
                    item.stance_justification = "Off-topic medical paper; does not evaluate workplace wage or labor rights."
                    return item

            # B. Filter out atmospheric / climate / planetary science literature
            if any(clim in snippet_lower or clim in (item.title or "").lower() for clim in ("surface temperature", "hadcrut", "global warming", "calentamiento", "climate change", "ephemerides", "geodesy", "geoid", "photosynthesis", "तापमान", "जलवाय")):
                if not any(lab in snippet_lower or lab in (item.title or "").lower() for lab in ("wage", "overtime", "flsa", "minimum wage", "labor", "workplace")):
                    item.relevance_status = "IRRELEVANT"
                    item.relevance_score = 0.0
                    item.relevance_justification = "Domain mismatch: atmospheric, climatological, or astronomical literature retrieved for workplace employment rights claim."
                    item.stance = "NEUTRAL"
                    item.stance_justification = "Off-topic physical science paper; does not evaluate workplace wage or labor rights."
                    return item

            # C. Filter out general criminal justice / incarceration statistics lacking labor or wage content
            if any(crim in snippet_lower or crim in (item.title or "").lower() for crim in ("incarceration gap", "incarceration rate", "arrest and conviction", "department of public safety", "crime rates between undocumented", "crime rate", "violent crime", "prisión", "delincuencia")):
                if not any(lab in snippet_lower or lab in (item.title or "").lower() for lab in ("wage", "overtime", "flsa", "minimum wage", "unpaid wages", "wage theft")):
                    item.relevance_status = "IRRELEVANT"
                    item.relevance_score = 0.0
                    item.relevance_justification = "Domain mismatch: general criminal incarceration or arrest rate statistics retrieved for workplace wage/labor claim."
                    item.stance = "NEUTRAL"
                    item.stance_justification = "General criminal justice dataset does not evaluate workplace wage theft or labor standards."
                    return item

            # D. Filter out macroeconomic fiscal studies lacking wage theft or labor standards content
            if any(wt in claim_lower for wt in ("wage theft", "robo de salario", "मजदूरी चोरी", "মজুরি চুরি", "unpaid wages", "cannot report", "reporting workplace")):
                if not any(w in snippet_lower or w in (item.title or "").lower() for w in ("wage", "overtime", "minimum wage", "unpaid", "flsa", "wage theft", "retaliation", "labor laws", "complaint", "discharge", "discriminate", "employee")):
                    item.relevance_status = "IRRELEVANT"
                    item.relevance_score = 0.0
                    item.relevance_justification = "Document discusses general macroeconomic or fiscal metrics but does not address workplace wage protections, wage theft, or labor standards."
                    item.stance = "NEUTRAL"
                    item.stance_justification = "Record does not address wage reporting or labor law enforcement; stance is strictly NEUTRAL."
                    return item

        # Step 2: Stance Decision (SUPPORTING, CONTRADICTING, or NEUTRAL)
        # Curator-verified stance preservation: human curation decisions take precedence over heuristic keyword counters.
        if item.curation_status == "APPROVED_VERIFIED" and (item.reviewer_confirmed_stance in ("SUPPORTING", "CONTRADICTING") or item.stance in ("SUPPORTING", "CONTRADICTING")):
            item.stance = item.reviewer_confirmed_stance or item.stance
            item.stance_justification = (
                f"Curator-verified stance preserved ({item.stance}). "
                f"Human curation review takes precedence over automated heuristic stance evaluation."
            )
            return item

        # Rule: Do not infer stance merely because the article discusses the same topic!
        has_refutation = any(marker in snippet_lower for marker in REFUTATION_MARKERS)
        has_affirmation = any(marker in snippet_lower for marker in AFFIRMATION_MARKERS)

        # Check if the claim itself has negative or inverse polarity (Multilingual: EN, ES, HI, BN)
        inverse_markers = [
            # English
            "not", "never", "no link", "does not", "false", "myth",
            "declined", "declining", "decreased", "decreasing", "cooled", "cooling", "ceased",
            # Spanish
            "no", "nunca", "jamás", "falso", "falsa", "mito", "bulo",
            "disminuyó", "disminuye", "redujo", "bajó", "enfrió",
            # Hindi
            "नहीं", "ना", "झूठ", "गलत", "घटा", "घटी", "गिरावट", "कमी", "ठंडा",
            # Bengali
            "না", "নয়", "নেই", "মিথ্যা", "ভুল", "হ্রাস", "কমেছে", "পতন",
        ]
        claim_is_negative = any(neg in claim_lower for neg in inverse_markers)

        if has_refutation and not has_affirmation:
            if claim_is_negative:
                item.stance = "SUPPORTING"
                item.stance_justification = (
                    "Evidence refutes the affirmative proposition, corroborating the submitted negative claim."
                )
            else:
                item.stance = "CONTRADICTING"
                item.stance_justification = (
                    "Evidence explicitly contradicts or refutes the claim proposition with contrary findings."
                )
        elif has_affirmation and not has_refutation:
            if claim_is_negative:
                item.stance = "CONTRADICTING"
                item.stance_justification = (
                    "Evidence affirms the proposition, contradicting the submitted negative claim."
                )
            else:
                item.stance = "SUPPORTING"
                item.stance_justification = (
                    "Evidence excerpt reports affirmative observational findings or empirical confirmation aligning with the claim."
                )
        elif has_refutation and has_affirmation:
            item.stance = "NEUTRAL"
            item.stance_justification = (
                "Evidence contains both affirmative and qualifying/refuting statements. "
                "Without conclusive consensus in the excerpt, stance is retained as NEUTRAL."
            )
        else:
            item.stance = "NEUTRAL"
            item.stance_justification = (
                "Source discusses the topic descriptively or contextually, but does not present an assertive "
                "empirical affirmation or refutation of the specific claim statement. Stance is retained as NEUTRAL."
            )

        return item
