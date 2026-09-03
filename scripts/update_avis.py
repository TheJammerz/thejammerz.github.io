#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recopie dans index.html les avis 5/5 AVEC commentaire de la fiche Google
Business Profile de The Jammerz.

Source de verite = Google. Le script ne fait QUE recopier ce qu'il recoit
(zero invention : pas d'avis fabrique, pas de note arrondie, pas de texte
reecrit). Il remplace le contenu entre les marqueurs
<!-- AVIS:AUTO:START ... --> et <!-- AVIS:AUTO:END --> dans index.html.


POURQUOI L'API « BUSINESS PROFILE » ET SURTOUT PAS L'API « PLACES »
------------------------------------------------------------------
Premiere version de ce script : API Places (New). Abandonnee, pour deux
raisons qui ne se discutent pas.

1. C'EST INTERDIT PAR CONTRAT. Les conditions Google Maps Platform, article
   3.2.3(a) « No Scraping » (version EEE : article 3.3.2), disent que le
   client ne doit pas « copier et enregistrer les noms d'entreprises, les
   adresses ou les avis d'utilisateurs ». Seul le place_id peut etre garde.
   Or un robot qui appelle Places chaque nuit et ecrit les avis dans
   index.html fait exactement ca : il copie et il enregistre. Une page qui
   affiche du Places doit rappeler l'API a chaque affichage, ce qui remet la
   cle dans le navigateur et rallonge le chargement — les deux choses qu'on
   voulait eviter.
2. C'EST PAYANT ET CA NE RAMENE QUE 5 AVIS. Le champ « reviews » bascule
   l'appel dans le palier « Enterprise + Atmosphere », et Places ne renvoie
   jamais plus de 5 avis, sans pagination ni filtre.

L'API Google Business Profile, elle, sert justement a gerer SA PROPRE fiche.
Elle est gratuite (« The Google My Business API is available to registered
users at no charge »), elle rend TOUS les avis avec leur texte, et on peut
donc garder uniquement les 5/5 avec commentaire, comme demande.

Prix a payer : elle demande une autorisation Google (formulaire « Application
for Basic API Access », reponse annoncee sous 14 jours) et un consentement
OAuth du proprietaire de la fiche. Il n'y a pas de cle simple, et les comptes
de service ne sont pas acceptes : c'est structurel, Google veut un humain
proprietaire derriere l'appel.


LES DEUX FACONS D'ALIMENTER LA PAGE
-----------------------------------
1. AUTOMATIQUE (une fois l'acces accorde) : les trois secrets GBP_* ci-dessous
   sont poses dans le depot, le robot appelle Google chaque nuit.
2. MANUELLE, DISPONIBLE TOUT DE SUITE : un export Google Takeout de la fiche
   (« Google Business Profile ») donne un fichier d'avis. On le pose dans
   data/avis_source.json et le script s'en sert. Gratuit, officiel, sans
   autorisation a attendre. A refaire a la main quand il y a de nouveaux avis.

Si aucune des deux sources n'est disponible, le script ne fait rien et laisse
la page exactement telle quelle.


Variables attendues (secrets du depot) :
  GBP_CLIENT_ID       identifiant OAuth du client « application de bureau »
  GBP_CLIENT_SECRET   son secret
  GBP_REFRESH_TOKEN   jeton long obtenu une seule fois avec scripts/avis_jeton.py
  GBP_ACCOUNT_ID      facultatif — ex. 123456789. Absent, le script cherche.
  GBP_LOCATION_ID     facultatif — ex. 987654321. Absent, le script cherche.

Lance 1x/jour par GitHub Actions (.github/workflows/avis.yml).
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------- #
# Adresses Google. Trois API distinctes, et c'est un piege : l'autorisation
# « Basic API Access » se demande par API. Etre accepte sur Business Profile
# ne donne PAS le quota sur Account Management, qui sert a trouver le numero
# de compte. D'ou GBP_ACCOUNT_ID / GBP_LOCATION_ID : les poser en secret evite
# completement les deux API de recherche.
# --------------------------------------------------------------------------- #
JETON = "https://oauth2.googleapis.com/token"
COMPTES = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
FICHES = "https://mybusinessbusinessinformation.googleapis.com/v1"
AVIS = "https://mybusiness.googleapis.com/v4"

START_MARK = "<!-- AVIS:AUTO:START"
END_MARK = "<!-- AVIS:AUTO:END -->"

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
# Le fichier d'export manuel (Takeout), s'il existe. Il est versionne : ce sont
# les avis de notre propre fiche, deja publics sur Google.
SOURCE_LOCALE = ROOT / "data" / "avis_source.json"

# Combien d'avis on garde au maximum dans la page. L'orbite en montre 6 a la
# fois et fait tourner les autres ; au-dela de 24 le bloc pese pour rien.
MAX_AVIS = 24
# Longueur max d'un commentaire recopie. Au-dela, la carte deviendrait illisible
# dans l'orbite. On coupe sur un espace et on met une vraie ellipse.
MAX_CAR = 300

# Ce que Google colle autour d'un avis ecrit dans une autre langue.
TRADUIT = "(Translated by Google)"
ORIGINAL = "(Original)"

# Google rend la note en toutes lettres dans cette API.
NOTES = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}

# Des clients commencent (ou finissent) leur avis par une rangee d'etoiles
# dessinees a la main : « ⭐⭐⭐⭐⭐ <retour a la ligne> Un groupe qui... ».
# La carte affiche DEJA les 5 etoiles au-dessus du texte : garder celles du
# client donnerait deux rangees l'une sous l'autre, et ces caracteres mangent
# la moitie des 4 lignes visibles. On les retire A L'AFFICHAGE seulement.
# ⚠️ On ne retire QUE de la decoration : pas un mot du client n'est touche.
DECOR = "⭐★☆✪✩✭✯✰\U0001f31f✨"
RANGEE_DEBUT = re.compile("^[\\s" + DECOR + "]+")
RANGEE_FIN = re.compile("[\\s" + DECOR + "]+$")

# Quand quelqu'un met une note SANS ecrire, Google ne laisse pas le champ vide :
# il ecrit cette phrase a la place. Sans ce garde-fou elle partirait en ligne
# comme un vrai temoignage. Consigne de Quentin : que des avis AVEC ecriture.
SANS_ECRITURE = (
    "n'a pas rédigé d'avis",
    "n'a pas redige d'avis",
    "didn't write a review",
    "did not write a review",
    "hasn't written a review",
)


def nettoyer(txt: str) -> str:
    """Retire la decoration autour du texte et refuse ce qui n'est pas ecrit.

    Rend "" quand il ne reste aucune lettre ni aucun chiffre : une rangee
    d'etoiles toute seule n'est pas un commentaire, c'est une note.
    """
    if not txt:
        return ""
    bas = txt.lower()
    for phrase in SANS_ECRITURE:
        if phrase in bas:
            return ""
    txt = RANGEE_FIN.sub("", RANGEE_DEBUT.sub("", txt))
    if not any(c.isalnum() for c in txt):
        return ""
    return txt.strip()


def dire(msg: str) -> None:
    print("[avis] " + msg, flush=True)


class PasEncoreAutorise(RuntimeError):
    """Google repond, mais le quota du projet vaut ZERO.

    C'est la situation normale entre le depot du formulaire « Application for
    Basic API Access » et la reponse de Google (annoncee sous 14 jours). Ce
    n'est PAS une panne : il ne faut ni rougir le workflow (sinon GitHub
    envoie un mail d'echec chaque nuit pendant deux semaines), ni toucher a la
    page. On la traite donc comme « aucune source branchee ».
    """


# --------------------------------------------------------------------------- #
# Appels Google
# --------------------------------------------------------------------------- #
def http(url: str, entetes: dict, corps: bytes | None = None,
         forme: str | None = None) -> dict:
    """Un appel HTTP qui rend du JSON. Leve une exception si Google n'est pas
    content : on veut que le workflow devienne rouge, pas qu'il echoue en
    silence."""
    req = urllib.request.Request(url, data=corps,
                                 method="POST" if corps else "GET")
    for k, v in entetes.items():
        req.add_header(k, v)
    if forme:
        req.add_header("Content-Type", forme)
    try:
        with urllib.request.urlopen(req, timeout=30) as rep:
            return json.loads(rep.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        indice = ""
        if e.code == 403:
            indice = (" — un 403 ici veut presque toujours dire « quota a 0 » :"
                      " l'acces a cette API precise n'a pas encore ete accorde.")
        if e.code == 401:
            indice = (" — un 401 veut dire jeton refuse. Si l'ecran de"
                      " consentement OAuth est reste en « Test », le jeton"
                      " expire au bout de 7 jours : il faut le publier en"
                      " « Production ».")
        # Quota a ZERO = acces pas encore accorde, pas une panne. Google le dit
        # dans le corps de la reponse ; l'espacement du JSON change parfois,
        # d'ou la comparaison sur une version sans espaces.
        if '"quota_limit_value":"0"' in "".join(detail.split()):
            raise PasEncoreAutorise(
                "quota a 0 sur %s : Google n'a pas encore accorde l'acces "
                "(formulaire « Application for Basic API Access »)."
                % url.split("/")[2])
        raise RuntimeError("Google repond %s : %s%s" % (e.code, detail, indice))


def acces(cid: str, secret: str, refresh: str) -> str:
    """Echange le jeton long contre un jeton d'acces valable 1 heure."""
    corps = urllib.parse.urlencode({
        "client_id": cid,
        "client_secret": secret,
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }).encode("utf-8")
    rep = http(JETON, {}, corps, "application/x-www-form-urlencoded")
    jeton = rep.get("access_token")
    if not jeton:
        raise RuntimeError("Google n'a pas renvoye de jeton d'acces")
    return jeton


def trouver_compte(jeton: str) -> str:
    """Numero du compte Business Profile. Demande le quota sur l'API Account
    Management, qui se demande separement."""
    rep = http(COMPTES + "?pageSize=20", {"Authorization": "Bearer " + jeton})
    comptes = rep.get("accounts") or []
    if not comptes:
        raise RuntimeError("aucun compte Business Profile visible avec ce jeton")
    for c in comptes:
        dire("compte : %s (%s)" % (c.get("accountName", "?"), c.get("name", "?")))
    nom = comptes[0].get("name", "")          # « accounts/123456789 »
    return nom.split("/")[-1]


def trouver_fiche(jeton: str, compte: str) -> str:
    """Numero de la fiche (l'etablissement) dans ce compte."""
    url = ("%s/accounts/%s/locations?readMask=name,title&pageSize=50"
           % (FICHES, compte))
    rep = http(url, {"Authorization": "Bearer " + jeton})
    lieux = rep.get("locations") or []
    if not lieux:
        raise RuntimeError("aucune fiche dans le compte %s" % compte)
    for l in lieux:
        dire("fiche : %s (%s)" % (l.get("title", "?"), l.get("name", "?")))
    return (lieux[0].get("name", "")).split("/")[-1]


def lire_avis(jeton: str, compte: str, fiche: str) -> list[dict]:
    """Tous les avis de la fiche, page par page (50 max par page)."""
    parent = "accounts/%s/locations/%s" % (compte, fiche)
    tous: list[dict] = []
    page = ""
    for _ in range(20):                       # garde-fou : 20 pages = 1000 avis
        url = "%s/%s/reviews?pageSize=50&orderBy=updateTime%%20desc" % (AVIS, parent)
        if page:
            url += "&pageToken=" + urllib.parse.quote(page)
        rep = http(url, {"Authorization": "Bearer " + jeton})
        tous.extend(rep.get("reviews") or [])
        page = rep.get("nextPageToken") or ""
        if not page:
            break
    return tous


# --------------------------------------------------------------------------- #
# Lecture d'un export manuel (Google Takeout)
# --------------------------------------------------------------------------- #
def lire_fichier(chemin: Path) -> list[dict]:
    """Un export Takeout. Le format bouge d'une annee sur l'autre : on accepte
    une liste nue, ou un objet qui contient une liste sous un nom courant."""
    # utf-8-sig : le Bloc-notes, Excel et PowerShell collent souvent un BOM
    # invisible en tete de fichier. Ce codec lit les deux cas.
    brut = json.loads(chemin.read_text(encoding="utf-8-sig"))
    if isinstance(brut, list):
        return [a for a in brut if isinstance(a, dict)]
    if isinstance(brut, dict):
        for cle in ("reviews", "avis", "locationReviews", "data"):
            val = brut.get(cle)
            if isinstance(val, list):
                return [a for a in val if isinstance(a, dict)]
    raise RuntimeError("%s : je ne trouve pas de liste d'avis dans ce fichier"
                       % chemin.name)


# --------------------------------------------------------------------------- #
# Mise en forme
# --------------------------------------------------------------------------- #
def texte_de(bloc) -> str:
    """Un champ texte est soit une chaine, soit {'text': ...} selon la source."""
    if isinstance(bloc, dict):
        return (bloc.get("text") or bloc.get("value") or "").strip()
    if isinstance(bloc, str):
        return bloc.strip()
    return ""


def note_de(avis: dict):
    """La note, quelle que soit la facon dont la source l'ecrit : « FIVE »
    (Business Profile), 5 (export ou service tiers), {'value': 5}."""
    brut = avis.get("starRating", avis.get("rating"))
    if isinstance(brut, dict):
        brut = brut.get("value", brut.get("rating"))
    if isinstance(brut, str):
        cle = brut.strip().upper()
        if cle in NOTES:
            return NOTES[cle]
        brut = cle
    try:
        return float(brut)
    except (TypeError, ValueError):
        return None


def commentaire_de(avis: dict) -> str:
    """Le texte de l'avis. Quand la langue de l'avis n'est pas celle de la
    fiche, Google colle les deux versions dans le meme champ :
    « (Translated by Google) ... (Original) ... ». On garde l'ORIGINAL :
    c'est le texte reellement ecrit par le client, pas une traduction machine
    — et la mention technique de Google n'a rien a faire sur une carte."""
    for cle in ("comment", "text", "originalText", "reviewText"):
        val = texte_de(avis.get(cle))
        if val:
            if TRADUIT in val and ORIGINAL in val:
                val = val.split(ORIGINAL, 1)[1].strip() or val
            # nettoyer() peut rendre "" : une note sans un mot ecrit n'est pas
            # un commentaire. On continue alors la boucle plutot que de rendre
            # "" tout de suite — le vrai texte est peut-etre dans un autre champ.
            val = nettoyer(val)
            if val:
                return val
    return ""


def auteur_de(avis: dict) -> dict:
    for cle in ("reviewer", "author", "authorAttribution"):
        val = avis.get(cle)
        if isinstance(val, dict):
            return val
    return {}


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
    if not isinstance(avis, dict):
        return False
    note = note_de(avis)
    if note is None or note < 5:
        return False
    return bool(commentaire_de(avis))


def jour(avis: dict) -> str:
    """La date au jour pres. Volontairement PAS « il y a 3 mois » : une phrase
    relative changerait toute seule chaque nuit et le robot recommiterait la
    page pour rien. C'est la page qui l'ecrit en clair au moment de l'afficher."""
    for cle in ("createTime", "publishTime", "date", "time", "createdAt"):
        val = avis.get(cle)
        if isinstance(val, str) and len(val) >= 10 and val[4] == "-":
            return val[:10]
    return ""


def convertir(avis: dict) -> dict:
    auteur = auteur_de(avis)
    nom = (auteur.get("displayName") or auteur.get("name") or "").strip()
    nom = nom or "Client Google"
    fiche = {
        "nom": nom,
        "texte": raccourcir(re.sub(r"\s+", " ", commentaire_de(avis))),
        "date": jour(avis),
        "ini": initiale(nom),
        "teinte": teinte(nom),
    }
    photo = (auteur.get("profilePhotoUrl") or auteur.get("photoUri") or "").strip()
    if photo.startswith("https://"):
        fiche["photo"] = photo
    return fiche


def bloc_json(avis: list[dict]) -> str:
    """Le bloc depose dans la page. Les avis voyagent en JSON : c'est le seul
    format ou un apostrophe, un guillemet ou un emoji d'un client ne peut pas
    casser la page."""
    charge = json.dumps(avis, ensure_ascii=False, indent=1, sort_keys=True)
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
def recuperer() -> list[dict] | None:
    """Rend la liste brute des avis, ou None si aucune source n'est branchee.
    None et [] ne veulent PAS dire la meme chose : None = « je n'ai rien
    demande a personne », [] = « on m'a repondu, et il n'y a rien »."""
    cid = (os.environ.get("GBP_CLIENT_ID") or "").strip()
    secret = (os.environ.get("GBP_CLIENT_SECRET") or "").strip()
    refresh = (os.environ.get("GBP_REFRESH_TOKEN") or "").strip()

    if cid and secret and refresh:
        dire("source : API Google Business Profile (gratuite).")
        try:
            jeton = acces(cid, secret, refresh)
            compte = (os.environ.get("GBP_ACCOUNT_ID") or "").strip()
            fiche = (os.environ.get("GBP_LOCATION_ID") or "").strip()
            if not compte:
                dire("pas de GBP_ACCOUNT_ID : je cherche le compte.")
                compte = trouver_compte(jeton)
                dire("compte retenu : %s (a coller en secret GBP_ACCOUNT_ID)"
                     % compte)
            if not fiche:
                dire("pas de GBP_LOCATION_ID : je cherche la fiche.")
                fiche = trouver_fiche(jeton, compte)
                dire("fiche retenue : %s (a coller en secret GBP_LOCATION_ID)"
                     % fiche)
            return lire_avis(jeton, compte, fiche)
        except PasEncoreAutorise as e:
            dire("%s" % e)
            dire("Les identifiants sont bons (Google a accepte le jeton), il "
                 "manque seulement le feu vert. J'attends, et je ne touche a "
                 "rien : la page garde les avis deja en ligne.")
            return None

    if SOURCE_LOCALE.exists():
        dire("source : export manuel %s." % SOURCE_LOCALE.name)
        return lire_fichier(SOURCE_LOCALE)

    dire("aucune source d'avis branchee : ni les trois secrets GBP_*, ni le "
         "fichier data/avis_source.json. La page reste telle quelle. (C'est le "
         "cas normal tant que l'acces Google n'a pas ete accorde.)")
    return None


def main() -> int:
    tous = recuperer()
    if tous is None:
        return 0

    retenus = [convertir(a) for a in tous if garder(a)]
    # Le plus recent d'abord, et ordre stable : sans ca le script recommiterait
    # la page chaque jour rien que parce que Google a change l'ordre.
    retenus.sort(key=lambda a: (a["date"], a["nom"]), reverse=True)
    retenus = retenus[:MAX_AVIS]
    dire("%d avis remontes, %d retenus (5/5 avec commentaire)."
         % (len(tous), len(retenus)))

    if not tous:
        dire("ATTENTION : la source n'a renvoye aucun avis. La page n'est PAS "
             "modifiee (on ne vide jamais la rubrique sur un simple silence).")
        return 0

    if not retenus:
        dire("ATTENTION : %d avis lus mais AUCUN retenu. Je n'ecris rien : "
             "c'est presque toujours un changement de format cote source, pas "
             "une vraie absence d'avis." % len(tous))
        return 1

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
