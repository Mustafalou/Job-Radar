"""Analyse d'une offre par un LLM (Azure AI Foundry), à partir de sa description.

Les alertes LinkedIn ne contiennent pas la description : on la colle à la main
dans le tableau de bord, puis ce module demande au modèle une note détaillée
par rapport à profile.md.

Variables d'environnement :
    AZURE_OPENAI_ENDPOINT    ex. https://<ressource>.openai.azure.com
    AZURE_OPENAI_API_KEY     facultatif : clé de la ressource. Absente = identité managée (recommandé)
    AZURE_OPENAI_DEPLOYMENT  nom du déploiement du modèle (défaut : gpt-4.1-mini)
    PROFILE_PATH             chemin de profile.md (défaut : profile.md à la racine du projet)
"""
import json
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

PROFILE_PATH = Path(os.getenv("PROFILE_PATH", Path(__file__).resolve().parents[2] / "profile.md"))
MAX_DESCRIPTION = 15_000  # caractères : une offre fait rarement plus, et ça borne le coût

SYSTEM_PROMPT = """Tu aides un candidat à trier des offres d'emploi.
On te donne son profil et une offre. Évalue honnêtement si l'offre lui correspond.
Règles :
- Base-toi uniquement sur le profil et l'offre. N'invente aucune compétence ni expérience.
- Une compétence listée "en cours d'apprentissage" n'est pas une compétence acquise.
- Une exigence bloquante (néerlandais courant, séniorité 5+ ans, domaine exclu) fait fortement baisser la note.
- Réponds en français, phrases courtes et simples.
Barème de la note (0 à 100) : 80+ = très bon match, postuler ; 60-79 = possible avec des écarts ;
40-59 = écarts importants ; moins de 40 = ne pas postuler."""

# Sortie structurée : le modèle doit renvoyer exactement ce JSON
SCHEMA = {
    "name": "job_analysis",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["score", "verdict", "strengths", "gaps", "blockers"],
        "properties": {
            "score": {"type": "integer", "description": "Note de 0 à 100"},
            "verdict": {"type": "string", "description": "Une phrase : postuler ou non, et pourquoi"},
            "strengths": {"type": "array", "items": {"type": "string"}, "description": "Points forts du candidat pour ce poste"},
            "gaps": {"type": "array", "items": {"type": "string"}, "description": "Compétences demandées qu'il n'a pas ou peu"},
            "blockers": {"type": "array", "items": {"type": "string"}, "description": "Exigences bloquantes (langue, séniorité...), vide si aucune"},
        },
    },
}


class LLMNotConfigured(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_client():
    """Client OpenAI pointé sur Azure (endpoint v1 de Foundry).

    Deux modes :
    - AZURE_OPENAI_API_KEY défini : authentification par clé (simple, pour le local) ;
    - sinon : identité managée de l'app (ou `az login` en local) via Microsoft Entra ID.
      Aucune clé stockée : l'app doit avoir le rôle "Cognitive Services OpenAI User" sur la ressource Foundry.
    """
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
        raise LLMNotConfigured("AZURE_OPENAI_ENDPOINT n'est pas défini")
    from openai import OpenAI
    # Garde seulement https://<ressource>.<domaine> : l'URL copiée depuis Foundry contient
    # parfois un chemin (/api/projects/..., /openai/...) qui donnerait une erreur 404
    u = urlparse(endpoint.strip())
    base_url = f"{u.scheme}://{u.netloc}/openai/v1/"
    key = os.getenv("AZURE_OPENAI_API_KEY")
    if key:
        return OpenAI(base_url=base_url, api_key=key)
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
    return OpenAI(base_url=base_url, api_key=token_provider)  # jeton renouvelé automatiquement


def load_profile(path: Path = PROFILE_PATH) -> str:
    return Path(path).read_text(encoding="utf-8")


def build_messages(job: dict, description: str, profile: str) -> list[dict]:
    offer = (
        f"Titre : {job.get('title')}\n"
        f"Entreprise : {job.get('company')}\n"
        f"Lieu : {job.get('location')} ({job.get('work_mode') or 'mode non précisé'})\n\n"
        f"Description :\n{description[:MAX_DESCRIPTION]}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"# PROFIL\n{profile}\n\n# OFFRE\n{offer}"},
    ]


def analyze_job(job: dict, description: str, client=None, profile: str | None = None) -> dict:
    """Renvoie {"score", "verdict", "strengths", "gaps", "blockers"}."""
    client = client or get_client()
    profile = profile if profile is not None else load_profile()
    resp = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini"),
        messages=build_messages(job, description, profile),
        response_format={"type": "json_schema", "json_schema": SCHEMA},
        temperature=0.2,
    )
    result = json.loads(resp.choices[0].message.content)
    result["score"] = max(0, min(100, int(result["score"])))
    return result
