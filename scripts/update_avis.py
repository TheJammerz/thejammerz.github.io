#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recopie dans index.html les avis 5/5 AVEC commentaire de la fiche Google
Business Profile de The Jammerz.

Source de verite = Google. Le script ne fait QUE recopier ce qu'il recoit
(zero invention : pas d'avis fabrique, pas de note arrondie, pas de texte
reecrit). Il remplace le contenu entre les marqueurs
<!-- AVIS:AUTO:START ... --> et <!-- AVIS:AUTO:END --> dans index.html.

Pourquoi passer par un script plutot que par la page :
  - la cle Google resterait visible par n'importe qui dans le code de la page,
    et n'importe qui pourrait s'en servir a nos frais ;
  - un appel reseau au chargement rallongerait l'affichage, alors qu'on vient
    justement de rendre le site rapide.
Ici la cle vit dans les secrets GitHub, l'appel a lieu 1x/jour cote serveur, et
la page ne fait que lire un bloc de texte deja ecrit.

Lance 1x/jour par GitHub Actions (.github/workflows/avis.yml).

Variables attendues (secrets du depot) :
  GOOGLE_MAPS_API_KEY   obligatoire — cle Google Cloud, API « Places API (New) »
  GOOGLE_PLACE_ID       facultatif  — identifiant de la fiche. Absent, le script
                                      la cherche par son nom (GOOGLE_PLACE_QUERY,
                                      « The Jammerz Bayonne » par defaut) et
                                      affiche l'identifiant trouve, a coller en
                                      secret pour figer le choix.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://places.googleapis.com/v1"
RECHERCHE = BASE + "/places:searchText"
FICHE = BASE + "/places/"

START_MARK = "<!-- AVIS:AUTO:START"
END_MARK = "<!-- AVIS:AUTO:END -->"

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"

# Combien d'avis on garde au maximum dans la page. L'orbite en montre 6 a la
# fois et fait tourner les autres ; au-dela de 24 le bloc pese pour rien.
MAX_AVIS = 24
# Longueur max d'un commentaire recopie. Au-dela, la carte deviendrait illisible
# dans l'orbite. On coupe sur un espace et on met une vraie ellipse.
MAX_CAR = 300


def dire(msg: str) -> None:
    print("[avis] " + msg, flush=True)


# --------------------------------------------------------------------------- #
# Appels Google
# --------------------------------------------------------------------------- #
def appel(url: str, cle: str, masque: str, corps: dict | None = None) -> dict:
    """Un appel a l'API Places. Leve une exception si Google n'est pas content :
    on veut que le workflow devienne rouge, pas qu'il echoue en silence."""
    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    req = urllib.request.Request(url, data=donnees, method="POST" if corps else "GET")
    req.add_header("X-Goog-Api-Key", cle)
    req.add_header("X-Goog-FieldMask", masque)
    if donnees is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as rep:
            return json.loads(rep.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        raise RuntimeError("Google repond %s : %s" % (e.code, detail)) from None


def trouver_fiche(cle: str, question: str) -> str:
    """Retrouve l'identifiant de la fiche a partir de son nom."""
    rep = appel(
        RECHERCHE, cle,
        "places.id,places.displayName,places.formattedAddress",
        {"textQuery": question, "languageCode": "fr", "regionCode": "FR",
         "maxResultCount": 5},
    )
    lieux = rep.get("places") or []
    if not lieux:
        raise RuntimeError("aucune fiche Google ne correspond a « %s »" % question)
    for lieu in lieux:
        nom = (lieu.get("displayName") or {}).get("text", "?")
        dire("candidat : %s — %s — %s"
             % (nom, lieu.get("formattedAddress", "?"), lieu.get("id", "?")))
    choisi = lieux[0].get("id")
    if not choisi:
        raise RuntimeError("la reponse de Google ne contient pas d'identifiant")
    dire("fiche retenue : %s (colle-la dans le secret GOOGLE_PLACE_ID pour "
         "figer ce choix)" % choisi)
    return choisi


# --------------------------------------------------------------------------- #
# Mise en forme
# --------------------------------------------------------------------------- #
def texte_de(bloc) -> str:
    """Un champ texte de l'API est soit {'text': ...}, soit une chaine."""
    if isinstance(bloc, dict):
        return (bloc.get("text") or "").strip()
    if isinstance(bloc, str):
        return bloc.strip()
    return ""


def raccourcir(txt: str) -> str:
    if len(txt) <= MAX_CAR:
        return txt
    coupe = txt[:MAX_CAR].rsplit(" ", 1)[0].rstrip(" ,;:.")
    return coupe + "…"


def initiale(nom: str) -> str:
    """Premiere lettre du nom, accents retires, en majuscule."""
    plat = unicodedata.normalize("NFD", nom)
    plat = "".join(c for c in plat if not unicodedata.combining(c))
    for c in plat:
        if c.isalnum():
            return c.upper()
    return "?"


def teinte(nom: str) -> int:
    """Une couleur d'avatar stable pour un nom donne : deux relances du script
    ne doivent pas produire un fichier different, sinon on commit pour rien."""
    total = 0
    for c in nom:
        total = (total * 31 + ord(c)) % 360
    return total


def garder(avis: dict) -> bool:
    """La consigne de Quentin : uniquement les 5/5 QUI ont un commentaire."""
    try:
        note = float(avis.get("rating"))
    except (TypeError, ValueError):
        return False
    if note < 5:
        return False
    return bool(texte_de(avis.get("text")) or texte_de(avis.get("originalText")))


def convertir(avis: dict) -> dict:
    auteur = avis.get("authorAttribution") or {}
    nom = (auteur.get("displayName") or "").strip() or "Client Google"
    txt = texte_de(avis.get("text")) or texte_de(avis.get("originalText"))
    fiche = {
        "nom": nom,
        "texte": raccourcir(re.sub(r"\s+", " ", txt)),
        "quand": (avis.get("relativePublishTimeDescription") or "").strip(),
        "ini": initiale(nom),
        "teinte": teinte(nom),
    }
    photo = (auteur.get("photoUri") or "").strip()
    if photo.startswith("https://"):
        fiche["photo"] = photo
    lien = (auteur.get("uri") or "").strip()
    if lien.startswith("https://"):
        fiche["url"] = lien
    fiche["_date"] = (avis.get("publishTime") or "")
    return fiche


def bloc_json(avis: list[dict]) -> str:
    """Le bloc depose dans la page. Les avis voyagent en JSON : c'est le seul
    format ou un apostrophe, un guillemet ou un emoji d'un client ne peut pas
    casser la page."""
    propre = []
    for a in avis:
        a = dict(a)
        a.pop("_date", None)
        # Le lien vers le profil Google du client ne sert a rien dans la page et
        # il permettrait a n'importe qui de remonter tous ses autres avis : on
        # ne publie que ce qu'on affiche.
        a.pop("url", None)
        propre.append(a)
    charge = json.dumps(propre, ensure_ascii=False, indent=1)
    # Un "</script>" ecrit par un client fermerait le bloc en plein milieu.
    # On neutralise tous les chevrons : JSON les relit sans broncher.
    charge = charge.replace("<", "\\u003c").replace(">", "\\u003e")
    lignes = [
        START_MARK + " — genere par scripts/update_avis.py, ne pas editer a la main -->",
        '<script type="application/json" id="avis-google">',
        charge,
        "</script>",
        END_MARK,
    ]
    return "\n        ".join(lignes)


def splice(page: str, bloc: str) -> str:
    d = page.find(START_MARK)
    f = page.find(END_MARK)
    if d == -1 or f == -1 or f < d:
        raise RuntimeError("marqueurs AVIS:AUTO introuvables dans index.html")
    return page[:d] + bloc + page[f + len(END_MARK):]


# --------------------------------------------------------------------------- #
def main() -> int:
    cle = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
    if not cle:
        dire("pas de cle GOOGLE_MAPS_API_KEY : rien a faire, la page reste "
             "telle quelle. (C'est le cas normal tant que la cle n'a pas ete "
             "ajoutee dans les secrets du depot.)")
        return 0

    place = (os.environ.get("GOOGLE_PLACE_ID") or "").strip()
    if not place:
        question = (os.environ.get("GOOGLE_PLACE_QUERY")
                    or "The Jammerz Bayonne").strip()
        dire("pas de GOOGLE_PLACE_ID : recherche de la fiche par son nom.")
        place = trouver_fiche(cle, question)

    rep = appel(FICHE + place, cle,
                "id,displayName,rating,userRatingCount,googleMapsUri,reviews")
    tous = rep.get("reviews") or []
    dire("fiche « %s » : %s avis remontes par Google (note %s sur %s avis au "
         "total)" % ((rep.get("displayName") or {}).get("text", "?"),
                     len(tous), rep.get("rating", "?"),
                     rep.get("userRatingCount", "?")))

    retenus = [convertir(a) for a in tous if garder(a)]
    # Le plus recent d'abord, et ordre stable : sans ca le script recommiterait
    # la page chaque jour rien que parce que Google a change l'ordre.
    retenus.sort(key=lambda a: (a["_date"], a["nom"]), reverse=True)
    retenus = retenus[:MAX_AVIS]
    dire("%d avis 5/5 avec commentaire retenus." % len(retenus))

    if not tous:
        dire("ATTENTION : Google n'a renvoye aucun avis. La page n'est PAS "
             "modifiee (on ne vide jamais la rubrique sur un simple silence).")
        return 0

    page = INDEX.read_text(encoding="utf-8")
    neuve = splice(page, bloc_json(retenus))
    if neuve == page:
        dire("rien de nouveau, index.html inchange.")
        return 0
    INDEX.write_text(neuve, encoding="utf-8")
    dire("index.html mis a jour.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as err:                     # noqa: BLE001
        dire("ECHEC : %s" % err)
        dire("index.html n'a pas ete touche.")
        sys.exit(1)
