#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenere la rubrique « Le repertoire » de index.html a partir de la set list
publiee par le VPS (elle-meme lue dans le Sheet « SETS - The Jammerz »).

Le trou que ce script bouche : les deux listes du repertoire etaient ecrites en
dur dans index.html. Le groupe modifiait sa set list dans le Sheet et le site
public ne bougeait pas. Desormais le Sheet est la seule source de verite.

Chaine complete :
    Sheet « SETS - The Jammerz »  ->  VPS (route publique setlist.json)
                                  ->  ce script (GitHub Actions)
                                  ->  index.html entre les marqueurs
                                      <!-- REPERTOIRE:AUTO:START ... --> et
                                      <!-- REPERTOIRE:AUTO:END -->

Pourquoi une URL publique et pas le Sheet directement : GitHub Actions n'a pas
les identifiants Google du groupe, et on ne met AUCUN secret dans un depot
public. Le VPS, lui, les a deja ; il expose donc un JSON en lecture seule.

DEUX REGLES QUI GOUVERNENT TOUT LE FICHIER
------------------------------------------
1. index.html n'est JAMAIS modifie sur un doute. Source injoignable, JSON
   invalide, liste vide, effondrement du nombre de morceaux : on sort sans
   toucher a une ligne. Le site public garde son dernier etat connu bon.
2. Un echec n'est JAMAIS muet. Une panne reseau passagere sort en 0 avec un
   « ::warning:: » (le run reste vert, on ne veut pas rougir a chaque
   redemarrage du VPS) ; tout probleme de FOND — source non configuree, JSON
   casse, onglet vide, marqueurs disparus — sort en 1 avec un « ::error:: »,
   donc un run rouge et un mail GitHub. Avant, ces cas sortaient en 0 : le
   repertoire pouvait rester gele des mois sans que personne le sache.

L'ADRESSE DE LA SOURCE N'EST PAS DANS CE FICHIER. Ce depot est public et le VPS
qui sert la set list heberge aussi d'autres services ; publier son adresse ici
reviendrait a en donner la carte. Elle vient du secret GitHub
JAMMERZ_SETLIST_URL (voir .github/workflows/repertoire.yml). Sans lui, le
script s'arrete net plutot que de deviner.

Zero invention : le script recopie les morceaux, il n'en complete ni n'en
devine aucun. Il ne sait pas non plus ecrire un titre a la place du groupe.

Lance 1x/jour par GitHub Actions (.github/workflows/repertoire.yml).

Test hors ligne (sert aussi a rejouer un incident) :
    python scripts/update_repertoire.py --source /chemin/vers/setlist.json
    JAMMERZ_SETLIST_URL=https://.../setlist.json python scripts/update_repertoire.py
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DELAI_RESEAU = 30                       # secondes avant d'abandonner la lecture

START_MARK = "<!-- REPERTOIRE:AUTO:START"
END_MARK = "<!-- REPERTOIRE:AUTO:END -->"

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"

# Les deux onglets du repertoire, dans l'ordre d'affichage. La cle est celle
# attendue dans le JSON ; elle sert aussi de valeur a data-tab-content, donc
# elle doit rester alignee sur les boutons .tab de index.html.
ONGLETS = ("principal", "secondaire")

# Garde-fou anti-absurdite : une set list de groupe fait quelques dizaines de
# titres. Au-dela, on suppose une source corrompue et on ne touche a rien.
LIMITE_MORCEAUX = 200

# Plancher anti-effondrement. Si la nouvelle set list fait moins que cette part
# de celle actuellement en ligne, on refuse de publier. Le scenario redoute :
# le Sheet est vide par erreur (ou une seule ligne survit a une fausse
# manoeuvre) et le site public affiche soudain un repertoire d'un morceau. Une
# vraie coupe reste possible, elle passe juste par une main humaine.
PART_MINI = 0.60
PLANCHER_IGNORE_SOUS = 10               # sous 10 morceaux en ligne, pas de plancher

# Au-dela, la set list servie par le VPS n'est plus rafraichie : on publie
# quand meme (c'est la derniere verite connue) mais on le SIGNALE.
JOURS_AVANT_PERIME = 14

# Le compteur « Morceaux au repertoire » de la rubrique « A propos ». C'est un
# chiffre precis affiche en public : il doit suivre le Sheet, pas une saisie
# d'il y a deux ans.
STAT_LABEL = "Morceaux au répertoire"
STAT_MOTIF = re.compile(
    r'(<div class="stat-num" data-count=")(\d+)(">)(\d+)(</div>\s*\n\s*'
    r'<div class="stat-label">' + re.escape(STAT_LABEL) + r"</div>)"
)


class Panne(Exception):
    """Probleme de fond : run rouge, index.html intact."""


class Passager(Exception):
    """Probleme reseau : run vert avec avertissement, index.html intact."""


def avertir(message: str) -> None:
    """Anomalie toleree. « ::warning:: » = visible dans le run, sans le casser."""
    print(f"::warning title=Repertoire::{message}")
    print(f"[repertoire] {message}", file=sys.stderr)


def signaler(message: str) -> None:
    """Anomalie de fond. « ::error:: » = run rouge, donc mail GitHub."""
    print(f"::error title=Repertoire::{message}")
    print(f"[repertoire] {message}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Lecture de la source (URL publique ou fichier local pour les tests)
# --------------------------------------------------------------------------- #
def lire_source(source: str) -> dict:
    """Renvoie les donnees, ou leve Panne / Passager.

    `source` est soit une URL http(s), soit un chemin de fichier local
    (porte de test : voir --source dans la docstring du module).
    """
    brut: bytes
    if source.startswith("http://") or source.startswith("https://"):
        try:
            requete = urllib.request.Request(
                source, headers={"User-Agent": "Mozilla/5.0 (jammerz-repertoire-bot)"}
            )
            with urllib.request.urlopen(requete, timeout=DELAI_RESEAU) as reponse:
                brut = reponse.read()
        except urllib.error.HTTPError as exc:
            # 4xx = la route a bouge ou le service refuse : c'est du fond.
            # 5xx = le serveur tousse : ca passera tout seul.
            if 400 <= exc.code < 500:
                raise Panne(f"source refusee (HTTP {exc.code}) — route changee ?")
            raise Passager(f"source en panne (HTTP {exc.code})")
        except Exception as exc:
            raise Passager(f"source injoignable ({type(exc).__name__})")
    else:
        chemin = Path(source)
        if not chemin.is_file():
            raise Panne(f"fichier source introuvable : {source}")
        try:
            brut = chemin.read_bytes()
        except Exception as exc:
            raise Panne(f"lecture impossible ({type(exc).__name__}) : {source}")

    try:
        donnees = json.loads(brut.decode("utf-8"))
    except Exception as exc:
        raise Panne(f"JSON invalide ({type(exc).__name__})")

    if not isinstance(donnees, dict):
        raise Panne("JSON invalide : objet attendu a la racine")
    return donnees


def extraire_onglet(donnees: dict, cle: str) -> list[dict]:
    """Les morceaux d'un onglet, normalises en {"morceau", "artiste"}.

    Une entree biscornue est ignoree et SIGNALEE, plutot que de casser tout le
    rendu : une coquille dans une ligne du Sheet ne doit pas priver le site des
    30 autres morceaux. En revanche un onglet entierement vide leve Panne : ca
    n'arrive pas par hasard, et publier une liste vide defigurerait la page.
    """
    liste = donnees.get(cle)
    if liste is None:
        raise Panne(f"cle « {cle} » absente du JSON")
    if not isinstance(liste, list):
        raise Panne(f"cle « {cle} » : liste attendue, {type(liste).__name__} recu")

    morceaux: list[dict] = []
    for rang, entree in enumerate(liste, start=1):
        if isinstance(entree, str):          # tolerance : titre seul, sans artiste
            titre, artiste = entree.strip(), ""
        elif isinstance(entree, dict):
            titre = champ_texte(entree.get("morceau"))
            artiste = champ_texte(entree.get("artiste"))
        else:
            avertir(f"{cle} : entree #{rang} ignoree (type {type(entree).__name__})")
            continue
        if titre is None or artiste is None:
            # str() sur un dict ou une liste publierait « {'a': 1} » en clair
            # sur le site. Mieux vaut une ligne en moins qu'une ligne absurde.
            avertir(f"{cle} : entree #{rang} ignoree (champ de type inattendu)")
            continue
        if not titre:
            avertir(f"{cle} : entree #{rang} ignoree (titre vide)")
            continue
        morceaux.append({"morceau": titre, "artiste": artiste})

    if not morceaux:
        raise Panne(f"onglet « {cle} » vide — set list a verifier dans le Sheet")
    if len(morceaux) > LIMITE_MORCEAUX:
        raise Panne(f"onglet « {cle} » : {len(morceaux)} morceaux, "
                    f"au-dela de la limite de securite ({LIMITE_MORCEAUX})")
    return morceaux


def champ_texte(valeur) -> str | None:
    """Une cellule du Sheet ramenee a du texte, ou None si elle n'en est pas.

    On accepte le texte, l'absence (cellule vide) et les nombres (« 99
    Luftballons » peut arriver en nombre). On refuse tout le reste : un dict ou
    une liste passes a str() donneraient du Python affiche en public.
    """
    if valeur is None:
        return ""
    if isinstance(valeur, str):
        return valeur.strip()
    if isinstance(valeur, bool):            # avant int : un bool EST un int
        return None
    if isinstance(valeur, (int, float)):
        return str(valeur).strip()
    return None


# --------------------------------------------------------------------------- #
# Rendu HTML
# --------------------------------------------------------------------------- #
def texte(valeur: str) -> str:
    """Echappement HTML d'une donnee venue de l'exterieur (Sheet -> VPS -> ici).

    quote=False : on ecrit du texte entre <li> et </li>, pas un attribut ; les
    apostrophes restent lisibles dans le source (« It's Your Life »).
    """
    return html.escape(valeur, quote=False)


def rendre_morceau(entree: dict) -> str:
    """Une ligne <li>. Le tiret cadratin ne s'affiche que s'il y a un artiste."""
    titre = texte(entree["morceau"])
    artiste = texte(entree["artiste"])
    libelle = f"{titre} — {artiste}" if artiste else titre
    return f"          <li>{libelle}</li>"


def rendre_onglet(cle: str, morceaux: list[dict], actif: bool) -> str:
    """Une liste <ul> complete, classes et data-* identiques a l'existant.

    « songs-active » n'est pose que sur le premier onglet : c'est l'etat initial
    de la page, app.js deplace ensuite la classe au clic sur les boutons .tab.
    """
    classes = "songs songs-active" if actif else "songs"
    lignes = [f'        <ul class="{classes}" data-tab-content="{cle}">']
    lignes += [rendre_morceau(m) for m in morceaux]
    lignes.append("        </ul>")
    return "\n".join(lignes)


def rendre_bloc(onglets: dict[str, list[dict]]) -> str:
    return "\n".join(
        rendre_onglet(cle, onglets[cle], actif=(indice == 0))
        for indice, cle in enumerate(ONGLETS)
    )


# --------------------------------------------------------------------------- #
# Injection dans index.html
# --------------------------------------------------------------------------- #
def bornes(html_text: str) -> tuple[int, int]:
    """(fin du marqueur d'ouverture, debut du marqueur de fermeture)."""
    debut = html_text.find(START_MARK)
    fin = html_text.find(END_MARK)
    if debut == -1 or fin == -1:
        raise Panne("marqueurs REPERTOIRE:AUTO introuvables dans index.html")
    if fin < debut:
        raise Panne("marqueurs REPERTOIRE:AUTO inverses dans index.html")
    tete_fin = html_text.find("-->", debut)
    if tete_fin == -1 or tete_fin > fin:
        raise Panne("marqueur REPERTOIRE:AUTO:START non ferme dans index.html")
    return tete_fin + len("-->"), fin


def compter_en_ligne(html_text: str) -> int:
    """Le nombre de morceaux actuellement publies, pour le plancher."""
    ouvre, ferme = bornes(html_text)
    return html_text.count("<li>", ouvre, ferme)


def splice(html_text: str, bloc: str) -> str:
    """Remplace ce qui est entre les marqueurs."""
    ouvre, ferme = bornes(html_text)
    return f"{html_text[:ouvre]}\n{bloc}\n        {html_text[ferme:]}"


def recaler_compteur(html_text: str, total: int) -> str:
    """Recale le compteur « Morceaux au repertoire » sur le total reel.

    Le chiffre etait fige a 35 alors que le Sheet en compte un autre : sur un
    site public, un chiffre precis qui ne colle pas est un mensonge, meme
    involontaire. S'il n'y a pas exactement une occurrence, on ne touche a rien
    et on le dit — on ne bricole pas un HTML qu'on ne reconnait plus.
    """
    trouves = STAT_MOTIF.findall(html_text)
    if len(trouves) != 1:
        avertir(f"compteur « {STAT_LABEL} » : {len(trouves)} occurrence(s) "
                "au lieu d'une — laisse tel quel")
        return html_text
    return STAT_MOTIF.sub(
        lambda m: f"{m.group(1)}{total}{m.group(3)}{total}{m.group(5)}", html_text)


# --------------------------------------------------------------------------- #
# Entree
# --------------------------------------------------------------------------- #
def source_demandee(argv: list[str]) -> str:
    """--source <x> ou --source=<x>, sinon le secret JAMMERZ_SETLIST_URL.

    Aucune valeur par defaut : l'adresse du VPS n'a rien a faire dans un depot
    public. Pas de secret configure = on s'arrete, on ne devine pas.
    """
    for indice, argument in enumerate(argv):
        if argument.startswith("--source="):
            return argument.split("=", 1)[1]
        if argument == "--source" and indice + 1 < len(argv):
            return argv[indice + 1]
    source = (os.environ.get("JAMMERZ_SETLIST_URL") or "").strip()
    if not source:
        raise Panne("source non configuree : renseigner le secret GitHub "
                    "JAMMERZ_SETLIST_URL (ou passer --source pour un test local)")
    return source


def verifier_fraicheur(donnees: dict) -> str:
    """Signale une set list que le VPS ne rafraichit plus. Renvoie la date lue.

    Sans ca, un VPS qui sert eternellement le meme fichier passe inapercu :
    le script reussit tous les jours, ne change rien, et tout le monde croit
    que le repertoire est a jour.
    """
    # Le VPS pose « avertissement » quand il n'a pas pu relire le Sheet et
    # ressert sa derniere copie. Le contenu reste bon, mais il fige : le taire
    # reviendrait a annoncer un repertoire a jour qui ne l'est plus.
    prevenu = str(donnees.get("avertissement", "")).strip()
    if prevenu:
        avertir(f"le VPS ressert une copie en cache ({prevenu[:120]})")

    genere_le = str(donnees.get("genere_le", "")).strip()
    if not genere_le:
        avertir("le JSON ne dit pas quand il a ete genere — fraicheur inconnue")
        return "date inconnue"
    try:
        quand = datetime.fromisoformat(genere_le.replace("Z", "+00:00"))
        if quand.tzinfo is None:
            quand = quand.replace(tzinfo=timezone.utc)
        jours = (datetime.now(timezone.utc) - quand).days
    except Exception:
        avertir(f"date de generation illisible : {genere_le}")
        return genere_le
    if jours >= JOURS_AVANT_PERIME:
        avertir(f"set list generee il y a {jours} jours ({genere_le}) : "
                "le VPS ne la rafraichit peut-etre plus")
    return genere_le


def travail(argv: list[str]) -> int:
    source = source_demandee(argv)
    # On n'affiche PAS l'URL : elle vient d'un secret et les journaux d'un
    # depot public sont lisibles par tout le monde.
    print("[repertoire] source : "
          + ("fichier local" if not source.startswith("http") else "route publique du VPS"))

    donnees = lire_source(source)
    genere_le = verifier_fraicheur(donnees)

    onglets = {cle: extraire_onglet(donnees, cle) for cle in ONGLETS}
    total = sum(len(v) for v in onglets.values())
    # Le compteur public annonce des MORCEAUX, pas des lignes : un titre joue
    # dans les deux sets (« Killing in the Name ») reste un seul morceau.
    distincts = len({m["morceau"].casefold()
                     for v in onglets.values() for m in v})
    print(f"[repertoire] set list generee le {genere_le}")
    for cle in ONGLETS:
        print(f"[repertoire] {cle} : {len(onglets[cle])} morceau(x)")
    if distincts != total:
        print(f"[repertoire] {total} lignes, {distincts} titres distincts "
              "(des morceaux figurent dans les deux sets)")

    try:
        original = INDEX.read_text(encoding="utf-8")
    except Exception as exc:
        raise Panne(f"lecture de index.html impossible ({type(exc).__name__})")

    en_ligne = compter_en_ligne(original)
    if en_ligne >= PLANCHER_IGNORE_SOUS and total < en_ligne * PART_MINI:
        raise Panne(
            f"effondrement refuse : {total} morceau(x) proposes contre {en_ligne} "
            f"en ligne (plancher {int(PART_MINI * 100)} %). Si la coupe est "
            "voulue, publier a la main une fois, le script reprendra ensuite.")

    modifie = recaler_compteur(splice(original, rendre_bloc(onglets)), distincts)

    if modifie == original:
        print("[repertoire] Aucun changement.")
        return 0

    try:
        INDEX.write_text(modifie, encoding="utf-8")
    except Exception as exc:
        raise Panne(f"ecriture de index.html impossible ({type(exc).__name__})")

    print(f"[repertoire] index.html mis a jour — {total} morceau(x) "
          f"(etait {en_ligne}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        return travail(argv)
    except Passager as exc:
        avertir(f"{exc} -> index.html laisse INTACT, on retentera demain.")
        return 0
    except Panne as exc:
        signaler(f"{exc} -> index.html laisse INTACT.")
        return 1
    except Exception as exc:                # filet : un bug ici ne doit pas
        signaler(f"erreur inattendue ({type(exc).__name__}: {exc}) "
                 "-> index.html laisse INTACT.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
