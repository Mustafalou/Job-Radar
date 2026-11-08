"""Étape 3a : score rapide (0 à 100) de chaque offre par rapport à mon profil.

Score final = similarité sémantique (embeddings) + règles métier.

1) Similarité sémantique (DÉJÀ ÉCRIT, lis et comprends)
   On encode le titre de l'offre et chaque poste visé avec un modèle multilingue
   (FR/EN/ES), puis on prend la similarité cosinus maximale.
   "Científico de datos" et "Data Scientist" sont donc proches, sans règle à écrire.

2) Règles métier (À TOI DE CODER `rule_adjustment`)
   - Mot exclu dans le titre (mechanical, firmware...) -> score forcé à 0
   - Séniorité (senior, lead, principal, head of...)    -> pénalité
   - Bonus pour junior / graduate                        -> bonus
   Pense à comparer en minuscules.
"""
import re
from functools import lru_cache

TARGET_ROLES = [
    "Data Scientist",
    "Machine Learning Engineer",
    "AI Engineer",
    "Junior AI Engineer",
    "Data Science Consultant",
    "Generative AI Engineer, LLM",
    "GenAI Engineer",
    "NLP Data Scientist",
]

# Sous-chaîne volontaire : "mechanical" attrape aussi "Electromechanical"
EXCLUDED = ["mechanical", "firmware", "structural", "civil", "electrical", "hardware",
            "embedded", "electronics", "phd", "test automation", "qa ",
            "internship", "stage ", "stagiaire", "prácticas"]
# Mots entiers (regex \b) : "lead" ne doit pas attraper "leadership"
SENIOR = ["senior", "sr", "lead", "principal", "head of", "director", "manager", "staff"]
JUNIOR = ["junior", "graduate", "entry level", "trainee"]
LANG_NL = ["dutch", "nederlands", "néerlandophone", "nl speaking"]


@lru_cache(maxsize=1)
def get_model():
    """Chargé une seule fois (lent au 1er appel : téléchargement ~450 Mo)."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


@lru_cache(maxsize=1)
def _target_embeddings():
    return get_model().encode(TARGET_ROLES, normalize_embeddings=True)


def semantic_score(title: str) -> float:
    """Similarité max entre le titre et les postes visés, ramenée entre 0 et 90."""
    emb = get_model().encode([title], normalize_embeddings=True)[0]
    sim = float((_target_embeddings() @ emb).max())  # cosinus car vecteurs normalisés
    return max(0.0, min(90.0, sim * 90))  # 90 max : laisse la place aux bonus


def _has_word(words: list[str], text: str) -> str | None:
    """Renvoie le premier mot de la liste présent comme mot entier dans text."""
    for w in words:
        if re.search(rf"\b{re.escape(w)}\b", text):
            return w
    return None


def rule_adjustment(title: str) -> tuple[float | None, list[str]]:
    """Renvoie (ajustement, raisons).

    - None si le poste est exclu (le score final sera 0)
    - sinon la somme des ajustements : senior -30 OU junior +10, langue NL -20
    """
    t = title.lower()
    for excl in EXCLUDED:
        if excl in t:
            return None, [f"exclu: {excl.strip()}"]

    adj, reasons = 0.0, []
    if _has_word(SENIOR, t):
        adj -= 30
        reasons.append("senior: -30")
    elif _has_word(JUNIOR, t):
        adj += 10
        reasons.append("junior: +10")
    if _has_word(LANG_NL, t):
        adj -= 20
        reasons.append("langue: NL -20")
    return adj, reasons


def score_job(title: str) -> tuple[float, list[str]]:
    adj, reasons = rule_adjustment(title)
    if adj is None:
        return 0.0, reasons
    return max(0.0, min(100.0, semantic_score(title) + adj)), reasons
