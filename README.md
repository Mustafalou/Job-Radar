# Job Radar

Veille d'offres d'emploi personnelle : lit mes alertes LinkedIn et Indeed reçues dans Gmail,
stocke les offres, les score par rapport à mon profil et m'envoie un résumé quotidien.
L'envoi des candidatures reste manuel.

## Stack
Python 3.13, API Gmail (lecture seule), SQLite, embeddings multilingues, LLM, FastAPI.

## Étapes
1. Lecture des alertes Gmail  <- en cours
2. Stockage SQLite
3. Scoring vs profil (embeddings + LLM)
4. API FastAPI + tableau de bord
5. Résumé quotidien par email
6. Génération CV / lettre et suivi des candidatures

## Installation
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
