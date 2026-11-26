"""CV adapté à une offre, construit UNIQUEMENT à partir de cv_base.json.

Le LLM ne rédige que deux choses : le titre sous le nom et le court profil.
Pour tout le reste, il renvoie des identifiants (expériences, puces, compétences)
pris dans la base : il peut choisir et ordonner, mais pas inventer.
Tout identifiant inconnu est ignoré, et les expériences "always" sont toujours présentes.

Variables d'environnement : CV_BASE_PATH (défaut : cv_base.json à la racine du projet),
CV_PHONE (téléphone affiché sur le CV, gardé hors de git).
"""
import json
import os
from html import escape
from pathlib import Path

from jobradar import llm_scoring

CV_BASE_PATH = Path(os.getenv("CV_BASE_PATH", Path(__file__).resolve().parents[2] / "cv_base.json"))

# Nombre minimum de puces par expérience (complété automatiquement si le LLM en donne moins)
MIN_BULLETS = {"freelance": 4, "jobradar": 3, "sony": 2, "thesis": 1}

SYSTEM_PROMPT = """Tu prépares un CV adapté à une offre d'emploi, à partir d'une base de faits vrais.
Règles strictes :
- Tu ne peux utiliser QUE les identifiants de la base (expériences, puces, catégories, compétences).
- Choisis les puces les plus utiles pour cette offre et mets les plus pertinentes en premier.
  Le CV doit remplir une page : 4 à 5 puces pour l'expérience freelance, 3 à 4 pour Job Radar,
  2 à 3 pour Sony. N'écarte une puce que si elle est vraiment hors sujet pour l'offre.
- Ordonne les catégories et les compétences selon l'offre. Une compétence absente de la base n'existe pas.
- language : "fr" si l'offre est en français, sinon "en".
- headline : une ligne courte. Commence par l'intitulé du poste tel qu'il est écrit dans l'offre
  (même ordre des mots), puis 3 ou 4 compétences de la base, séparées par " · ".
- summary : 3 phrases maximum, à la première personne, ton simple et posé, sans exagération,
  sans tiret long. N'utilise que des faits présents dans la base, et cite des choses concrètes :
  son master, son stage ML chez Sony, son agent LLM avec serveur MCP sur Muskl, Job Radar sur Azure.
  Garde les noms techniques tels quels (écris "MCP", ne les traduis pas).
  Ne prétends jamais avoir livré un projet IA à un client : l'IA a été faite sur ses propres projets.
  Interdit : les phrases creuses du type "motivé pour apprendre", "environnement collaboratif",
  "innovant", "dynamique", "passionné". Termine plutôt par ce qu'il peut apporter sur ce poste.
- missing : les compétences demandées par l'offre qui ne sont pas dans la base (pour information)."""

SCHEMA = {
    "name": "cv_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["language", "headline", "summary", "experiences", "skills", "missing"],
        "properties": {
            "language": {"type": "string", "enum": ["fr", "en"]},
            "headline": {"type": "string"},
            "summary": {"type": "string"},
            "experiences": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["id", "bullets"],
                "properties": {"id": {"type": "string"}, "bullets": {"type": "array", "items": {"type": "string"}}}}},
            "skills": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["id", "items"],
                "properties": {"id": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}}}},
            "missing": {"type": "array", "items": {"type": "string"}},
        },
    },
}


def load_base(path: Path = CV_BASE_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _base_for_prompt(base: dict) -> str:
    """Version compacte de la base pour le LLM (sans les coordonnées)."""
    lines = []
    for e in base["experiences"]:
        lines.append(f"EXPERIENCE id={e['id']} : {e['role']['en']} | {e['org']['en']} | {e['dates']['en']}")
        for b in e["bullets"]:
            lines.append(f"  PUCE id={b['id']} : {b['en']}")
    for s in base["skills"]:
        lines.append(f"CATEGORIE id={s['id']} ({s['label']['en']}) : " + " | ".join(s["items"]))
    lines.append(f"EN COURS D'APPRENTISSAGE (pas acquis) : {base['learning']['en']}")
    lines.append(f"LANGUES : {base['languages']['en']}")
    lines.append(f"FORMATION : {base['education']['degree']['en']}, {base['education']['school']['en']}, {base['education']['year']}")
    return "\n".join(lines)


def clean_plan(plan: dict, base: dict) -> dict:
    """Garde seulement ce qui existe dans la base (garde-fou contre les inventions)."""
    exps = {e["id"]: e for e in base["experiences"]}
    out_exps, seen = [], set()
    for item in plan.get("experiences", []):
        e = exps.get(item["id"])
        if not e or e["id"] in seen:
            continue
        valid = {b["id"] for b in e["bullets"]}
        bullets = [b for b in dict.fromkeys(item["bullets"]) if b in valid]
        # Si le LLM a été trop avare, on complète avec les puces suivantes de la base
        # (le CV doit remplir une page, et ces puces sont vraies de toute façon)
        for b in e["bullets"]:
            if len(bullets) >= min(MIN_BULLETS.get(e["id"], 1), len(e["bullets"])):
                break
            if b["id"] not in bullets:
                bullets.append(b["id"])
        out_exps.append({"id": e["id"], "bullets": bullets})
        seen.add(e["id"])
    for e in base["experiences"]:  # expériences obligatoires oubliées : ajoutées avec toutes leurs puces
        if e.get("always") and e["id"] not in seen:
            out_exps.append({"id": e["id"], "bullets": [b["id"] for b in e["bullets"]]})
    # ordre chronologique conservé pour les expériences (le LLM choisit seulement le contenu)
    order = [e["id"] for e in base["experiences"]]
    out_exps.sort(key=lambda x: order.index(x["id"]))

    cats = {s["id"]: s for s in base["skills"]}
    out_skills, seen = [], set()
    for item in plan.get("skills", []):
        s = cats.get(item["id"])
        if not s or s["id"] in seen:
            continue
        items = [i for i in dict.fromkeys(item["items"]) if i in s["items"]]
        if items:
            out_skills.append({"id": s["id"], "items": items})
            seen.add(s["id"])

    return {
        "language": plan.get("language") if plan.get("language") in ("fr", "en") else "en",
        "headline": plan.get("headline", ""),
        "summary": plan.get("summary", ""),
        "experiences": out_exps,
        "skills": out_skills,
        "missing": plan.get("missing", []),
    }


def generate_plan(job: dict, description: str, client=None, base: dict | None = None) -> dict:
    client = client or llm_scoring.get_client()
    base = base or load_base()
    offer = (f"Titre : {job.get('title')}\nEntreprise : {job.get('company')}\nLieu : {job.get('location')}\n\n"
             f"Description :\n{description[:llm_scoring.MAX_DESCRIPTION]}")
    resp = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"# BASE DE FAITS\n{_base_for_prompt(base)}\n\n# OFFRE\n{offer}"},
        ],
        response_format={"type": "json_schema", "json_schema": SCHEMA},
        temperature=0.2,
    )
    return clean_plan(json.loads(resp.choices[0].message.content), base)


LABELS = {
    "fr": {"profile": "Profil", "exp": "Expérience", "skills": "Compétences techniques", "learning": "En cours d'approfondissement",
           "edu": "Formation", "lang": "Langues", "print": "Imprimer / PDF", "edit": "Clique sur un texte pour le modifier avant d'imprimer.",
           "missing": "Demandé dans l'offre mais absent de ta base (non ajouté au CV)"},
    "en": {"profile": "Profile", "exp": "Experience", "skills": "Technical Skills", "learning": "Currently deepening",
           "edu": "Education", "lang": "Languages", "print": "Imprimer / PDF", "edit": "Clique sur un texte pour le modifier avant d'imprimer.",
           "missing": "Demandé dans l'offre mais absent de ta base (non ajouté au CV)"},
}


def render_html(plan: dict, base: dict, job: dict) -> str:
    """Page A4 imprimable. Tous les textes passent par escape()."""
    lg = plan["language"]
    L = LABELS[lg]
    colon = " :" if lg == "fr" else ":"  # typographie française : espace avant les deux-points
    c = base["contact"]
    # Le téléphone reste hors de git : il vient d'un secret Container Apps (CV_PHONE)
    contact_line = [c["location"][lg], os.getenv("CV_PHONE") or c.get("phone"), c.get("email"), c.get("website")]
    contact_line = [x for x in contact_line if x]
    exps = {e["id"]: e for e in base["experiences"]}
    cats = {s["id"]: s for s in base["skills"]}

    parts = []
    for item in plan["experiences"]:
        e = exps[item["id"]]
        bullets = {b["id"]: b[lg] for b in e["bullets"]}
        parts.append(
            f'<div class="row"><div><span class="role">{escape(e["role"][lg])}</span> '
            f'<span class="org">| {escape(e["org"][lg])}</span></div><div class="date">{escape(e["dates"][lg])}</div></div>'
        )
        if item["bullets"]:
            parts.append("<ul>" + "".join(f"<li>{escape(bullets[b])}</li>" for b in item["bullets"]) + "</ul>")
    skills = "".join(
        f'<li><b>{escape(cats[s["id"]]["label"][lg])}{colon}</b> {escape(", ".join(s["items"]))}</li>' for s in plan["skills"]
    )
    missing = ""
    if plan["missing"]:
        missing = (f'<div class="note no-print"><b>{L["missing"]} :</b> '
                   f'{escape(", ".join(plan["missing"]))}</div>')
    ed = base["education"]
    title = f'CV {c["name"]} - {job.get("company") or ""}'
    return f"""<!doctype html><html lang="{lg}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<style>
@page{{size:A4;margin:8mm 13mm}}
body{{font-family:"Lato","Helvetica Neue",Arial,sans-serif;color:#1f2430;font-size:9.2pt;line-height:1.3;margin:0 auto;max-width:190mm;padding:0 12px}}
h1{{font-size:21pt;color:#14213d;margin:0}}
.sub{{color:#555;font-size:11pt;margin:2px 0}}
.contact{{color:#666;font-size:9pt;margin-bottom:8px}}
h2{{font-size:10.5pt;color:#14213d;text-transform:uppercase;letter-spacing:.3px;border-bottom:1.3px solid #14213d;padding-bottom:2px;margin:9px 0 4px;break-after:avoid}}
.row{{display:flex;justify-content:space-between;gap:8px;break-after:avoid}}
.role{{font-weight:700}}.org{{color:#555}}.date{{color:#555;font-size:9.5pt;white-space:nowrap}}
ul{{margin:2px 0 6px 0;padding-left:16px;break-inside:avoid}}li{{margin:1px 0}}p{{margin:2px 0}}
.skills li b{{color:#14213d}}
[contenteditable]:hover{{outline:1px dashed #1E4FD8}}
.toolbar{{position:sticky;top:0;background:#f3f6ff;border:1px solid #d6e0ff;border-radius:8px;padding:8px 12px;margin:10px 0;
  font:13px system-ui;display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
.toolbar button{{font:14px system-ui;padding:6px 12px;cursor:pointer}}
.note{{font:12px system-ui;color:#8a5a00;background:#fff7e6;border:1px solid #ffe1a6;border-radius:6px;padding:6px 10px;margin:6px 0}}
@media print{{.no-print{{display:none}} body{{padding:0;max-width:none}} [contenteditable]:hover{{outline:none}}}}
</style></head><body>
<div class="toolbar no-print"><button onclick="window.print()"><b>{L["print"]}</b></button><span>{L["edit"]}</span></div>
{missing}
<div contenteditable="true" spellcheck="true">
<h1>{escape(c["name"])}</h1>
<div class="sub">{escape(plan["headline"])}</div>
<div class="contact">{" · ".join(escape(x) for x in contact_line)}</div>
<h2>{L["profile"]}</h2>
<p>{escape(plan["summary"])}</p>
<h2>{L["exp"]}</h2>
{"".join(parts)}
<h2>{L["skills"]}</h2>
<ul class="skills">{skills}<li><b>{L["learning"]}{colon}</b> {escape(base["learning"][lg])}</li></ul>
<h2>{L["edu"]}</h2>
<div class="row"><div><span class="role">{escape(ed["degree"][lg])}</span> <span class="org">| {escape(ed["school"][lg])}</span></div><div class="date">{escape(ed["year"])}</div></div>
<p>{escape(ed["detail"][lg])}</p>
<h2>{L["lang"]}</h2>
<p>{escape(base["languages"][lg])}</p>
</div>
</body></html>"""
