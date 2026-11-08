"""Étape 1b : extraire les offres d'un email d'alerte LinkedIn.

À TOI DE CODER `parse_linkedin_alert`.

Structure observée dans les emails (une offre = un bloc) :

    <a href="https://www.linkedin.com/comm/jobs/view/4480992193/?trackingId=..."
       class="font-bold text-md ...">  Consultant in Data Science  </a>
    ...
    <p class="text-system-gray-100 text-xs ...">  Sia · Bruxelles (Hybride)  </p>

Pistes :
- BeautifulSoup : soup.find_all("a", href=...) avec un filtre sur "/comm/jobs/view/".
- Le même lien d'offre peut apparaître plusieurs fois (logo, titre...) : garde
  seulement le <a> qui a la classe "font-bold" et dédoublonne par job_id.
- L'id est le nombre après /jobs/view/ (regex r"/jobs/view/(\\d+)").
- La ligne "Entreprise · Lieu (Mode)" est dans le <p> qui suit le lien
  (indice : a.find_next("p")). Sépare sur " · ", puis extrais le mode entre
  parenthèses s'il existe (Hybride, Sur site, À distance), sinon None.
- Construis une URL propre sans tracking : https://www.linkedin.com/jobs/view/<id>/
"""
from dataclasses import dataclass


@dataclass
class Job:
    job_id: str
    title: str
    company: str
    location: str
    work_mode: str | None
    url: str
    source: str = "linkedin"


def parse_linkedin_alert(html: str) -> list[Job]:
    raise NotImplementedError("À toi de jouer !")
