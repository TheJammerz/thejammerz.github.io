#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Garde-fou SEO du site The Jammerz (https://thejammerz.com). Python standard uniquement.

    python scripts/check_seo.py            HORS LIGNE : lit les fichiers du dépôt.
                                           Code retour 1 si un problème BLOQUANT, sinon 0.
                                           (c'est ce que lance le hook git pre-push)
    python scripts/check_seo.py --live     EN LIGNE : interroge le vrai site.
                                           Code retour 1 si une « panne », sinon 0.
    python scripts/check_seo.py --json     comme --live, mais imprime la liste des
                                           problèmes en JSON (code retour 1 si une
                                           « panne », sinon 0).
    python scripts/check_seo.py --commit <sha>
                                           HORS LIGNE sur le contenu EXACT d'un commit
                                           (git archive) : ce que le hook pre-push
                                           contrôle, pas la copie de travail.
    Options : --timeout 20 (secondes, en ligne) · --racine <dossier> (hors ligne,
              pour contrôler une autre copie du dépôt).

Réutilisable depuis un autre programme :
    import check_seo
    problemes = check_seo.live_problems(timeout=20)
    # -> [{"key": str, "level": "panne"|"surveil", "titre": str, "detail": str}, ...]
    # liste vide = tout va bien. Ne lève jamais d'exception réseau.

Contrôle « page indexable oubliée du sitemap » : fichiers volontairement IGNORÉS
  - 404.html : page d'erreur, GitHub Pages la sert avec le code 404 (jamais indexée) ;
  - googleXXXX.html (hexadécimal, à la racine) : validation Search Console (aucun à
    ce jour : la validation passe par la balise meta de l'accueil) ;
  - tout dossier commençant par « . » ou « _ » (.git, .github...) : non publié ;
  - scripts/ (outillage Python), assets/ (images), data/ (JSON) : pas des pages.
Le contrôle « page noindex » regarde, lui, TOUS les HTML (sauf .git) : seules les
pages de NOINDEX_AUTORISES ont le droit de porter noindex.
"""
import argparse
import datetime
import html as _html
import http.client
import io
import json
import os
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

DOMAINE = "thejammerz.com"
BASE = "https://thejammerz.com/"
ANCIEN = "thejammerz.github.io"
HOTES_MAISON = {DOMAINE, "www." + DOMAINE, ANCIEN}
SITEMAP_URL = BASE + "sitemap.xml"
VERIF_GOOGLE = "8_JP_5pQg61sgcOULtnFcHBbuEE1riHzys-wRygYanQ"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
RACINE_DEFAUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Jamais parcourus (internes, jamais publiés).
DOSSIERS_JAMAIS = {".git", "node_modules", "__pycache__"}
# Dossiers publiés d'annexes (lecteur embarqué, etc.) : un HTML oublié y est une simple alerte,
# et il a le droit d'y porter noindex.
DOSSIERS_ANNEXES = ("assets", "data", "scripts")
# Directives robots qui prennent une valeur après « : » (pas un nom de robot).
# (unavailable_after n'y est PAS : une date d'expiration = noindex à terme.)
_DIRECTIVES_A_VALEUR = ("max-snippet", "max-image-preview", "max-video-preview")
UA = "TheJammerz-ControleSEO/1.0 (+https://thejammerz.com/)"

# Les SEULES pages qui ont le droit de porter noindex (voulu).
NOINDEX_AUTORISES = ("404.html", "conditions/index.html", "confidentialite/index.html")
# Les pages qui DOIVENT rester dans le sitemap (en retirer une = geste volontaire :
# on l'enlève aussi de cette liste, dans le même commit).
PAGES_ATTENDUES = tuple(BASE + p for p in (
    "", "concerts/", "mariage/", "soiree-entreprise/", "sud-landes/", "zones/",
    "zones/anglet/", "zones/tarnos/", "zones/biarritz/", "zones/saint-jean-de-luz/",
    "zones/capbreton/", "zones/cambo-les-bains/", "zones/hossegor/",
    "zones/saint-vincent-de-tyrosse/", "zones/hendaye/", "zones/soustons/", "zones/dax/",
    "zones/orthez/", "zones/pau/", "zones/mont-de-marsan/"))
# Fichiers texte publiés où l'ancienne adresse ne doit jamais réapparaître.
_EXT_TEXTE = (".html", ".htm", ".js", ".mjs", ".css", ".txt", ".xml", ".json",
              ".webmanifest", ".md", ".svg")


# --------------------------------------------------------------------------
# Outils communs (hors ligne + en ligne)
# --------------------------------------------------------------------------
_BALISES_HEAD = {"html", "head", "title", "meta", "link", "script", "style", "base",
                 "noscript", "template"}


class _AnalyseHTML(HTMLParser):
    """Relève dans une page : canoniques, meta robots, og:url, hreflang,
    blocs JSON-LD, tous les href et la balise de validation Google."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.canoniques, self.robots, self.og_url = [], [], []
        self.hreflang, self.hrefs, self.verif, self.ld_blocs = [], [], [], []
        self.canon_hors_head, self.refresh, self.bases, self.scripts = [], [], [], []
        self._ld, self._ld_json = None, False
        self._corps = False  # vrai dès qu'on a quitté le <head>

    def handle_starttag(self, tag, attrs):
        a = {}
        for k, v in attrs:
            a.setdefault(k.lower(), v if v is not None else "")
        if tag == "body" or tag not in _BALISES_HEAD:
            self._corps = True  # comme Google : une balise de contenu referme le <head>
        if tag == "link":
            rels = a.get("rel", "").lower().split()
            if "canonical" in rels:
                # Google ignore une canonique placée dans le <body>
                (self.canon_hors_head if self._corps else self.canoniques).append(
                    a.get("href", "").strip())
            if "alternate" in rels and "hreflang" in a:
                self.hreflang.append(a.get("href", ""))
        elif tag == "meta":
            nom = a.get("name", "").strip().lower()
            equiv = a.get("http-equiv", "").strip().lower()
            if nom in ("robots", "googlebot") or equiv == "x-robots-tag":
                self.robots.append(a.get("content", ""))
            elif nom == "google-site-verification" and not self._corps:
                self.verif.append(a.get("content", "").strip())
            if equiv == "refresh":
                self.refresh.append(a.get("content", ""))
            if "og:url" in (a.get("property", "").strip().lower(), nom):
                self.og_url.append(a.get("content", ""))
        elif tag == "base" and "href" in a:
            self.bases.append(a["href"])
        elif tag == "script":
            self._ld = []
            self._ld_json = a.get("type", "").strip().lower() == "application/ld+json"
        if "href" in a:
            self.hrefs.append(a["href"])

    def handle_data(self, data):
        if self._ld is not None:
            self._ld.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._ld is not None:
            (self.ld_blocs if self._ld_json else self.scripts).append("".join(self._ld))
            self._ld = None


def _analyser(html):
    p = _AnalyseHTML()
    p.feed(html)
    p.close()
    return p


def _dit_noindex(textes):
    """Vrai si une des valeurs robots (meta ou en-tête X-Robots-Tag) interdit l'indexation."""
    for texte in textes:
        for tok in re.split(r"[,;\s]+", (texte or "").lower()):
            tok = tok.strip()
            if ":" in tok:  # « googlebot: noindex » ; ignore « max-image-preview:none »
                avant, _, apres = tok.partition(":")
                avant = avant.strip()
                if avant in _DIRECTIVES_A_VALEUR:
                    continue
                if avant == "unavailable_after":
                    return True
                tok = apres.strip()
            if tok in ("noindex", "none", "unavailable_after"):
                return True
    return False


def _normaliser(texte):
    """Texte tel qu'un navigateur/Google le comprend : entités HTML (&#46;), « \\/ »
    et « \\u002e » du JSON/JS, puis %2E des URL. Sert à débusquer une adresse cachée."""
    t = _html.unescape(texte or "")
    t = t.replace("\\/", "/")
    t = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), t)
    try:
        t = unquote(t)
    except Exception:
        pass
    return t


def _sans_commentaires(texte):
    """Retire les commentaires HTML (invisibles pour Google) en gardant les numéros de ligne."""
    return re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), texte, flags=re.S)


def _lignes_ancien(texte, est_html=True):
    """Lignes (1..) où l'ancienne adresse thejammerz.github.io apparaît, même camouflée."""
    if est_html:
        texte = _sans_commentaires(texte)
    return [i for i, l in enumerate(texte.splitlines(), 1) if ANCIEN in _normaliser(l).lower()]


def _pages_jsonld(obj):
    """Les objets JSON-LD de type *Page (WebPage, AboutPage...) qui ont une « url »."""
    if isinstance(obj, dict):
        t = obj.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(isinstance(x, str) and x.endswith("Page") for x in types) and \
                isinstance(obj.get("url"), str):
            yield obj
        for v in obj.values():
            yield from _pages_jsonld(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _pages_jsonld(x)


def _souci_hote(url):
    """None si l'URL ne vise pas le site, ou vise bien https://thejammerz.com.
    Sinon, un texte qui dit ce qui cloche."""
    u = (url or "").strip()
    proto_relatif = u.startswith("//")
    try:
        parts = urlsplit("https:" + u if proto_relatif else u)
        hote = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None
    if hote not in HOTES_MAISON:  # autres sous-domaines (boutique.…) = autres sites, légitimes
        return None
    if hote == ANCIEN:
        return "ancienne adresse github.io"
    if proto_relatif:
        return "adresse sans https:// (//...)"
    if parts.scheme != "https":
        return "en %s:// au lieu de https://" % parts.scheme
    if hote != DOMAINE:
        return "hôte %s au lieu de %s" % (hote, DOMAINE)
    if port not in (None, 443):
        return "port %s inattendu" % port
    return None


def _urls_jsonld(obj):
    """Toutes les valeurs texte des clés "url" et "@id", à toute profondeur."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("url", "@id"):
                if isinstance(v, str):
                    yield v
                elif isinstance(v, list):
                    for x in v:
                        if isinstance(x, str):
                            yield x
            yield from _urls_jsonld(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _urls_jsonld(x)


def _lignes_de(texte, motif):
    """Numéros de ligne (1..) où le motif (texte simple, insensible à la casse) apparaît."""
    m = motif.lower()
    return [i for i, l in enumerate(texte.splitlines(), 1) if m in l.lower()]


def _pb(key, level, titre, detail):
    return {"key": key, "level": level, "titre": titre, "detail": detail}


# --------------------------------------------------------------------------
# MODE HORS LIGNE
# --------------------------------------------------------------------------
def _lire(chemin):
    with open(chemin, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def _fichier_de_loc(racine, loc):
    """'/' -> index.html ; '/x/y/' -> x/y/index.html. Vérifie la casse exacte
    (GitHub Pages distingue Zones/ et zones/, Windows non).
    Renvoie (chemin_relatif, souci ou None)."""
    chemin = unquote(urlsplit(loc).path)
    comps = [c for c in chemin.split("/") if c]
    if any(c in (".", "..") or "\\" in c for c in comps):
        return None, "chemin invalide"
    comps.append("index.html")
    rel = "/".join(comps)
    raison = _raison_ignoree(rel, not os.path.exists(os.path.join(racine, ".nojekyll")))
    if raison and raison.startswith("dossier"):
        return rel, "%s : GitHub Pages ne la servira pas" % raison
    cur = racine
    for c in comps:
        try:
            noms = os.listdir(cur)
        except OSError:
            return rel, "fichier %s absent" % rel
        if c not in noms:
            if c.lower() in (n.lower() for n in noms):
                return rel, "fichier %s : la casse ne correspond pas (GitHub Pages y est sensible)" % rel
            return rel, "fichier %s absent" % rel
        cur = os.path.join(cur, c)
    if not os.path.isfile(cur):
        return rel, "fichier %s absent" % rel
    return rel, None


def _url_de_fichier(rel):
    if rel == "index.html":
        return BASE
    if rel.endswith("/index.html"):
        return BASE + rel[:-len("index.html")]
    return BASE + rel


def _tous_les_html(racine):
    for dossier, sous, noms in os.walk(racine):
        sous[:] = sorted(d for d in sous if d not in DOSSIERS_JAMAIS)
        for n in sorted(noms):
            if n.lower().endswith((".html", ".htm")):
                rel = os.path.relpath(os.path.join(dossier, n), racine)
                yield rel.replace(os.sep, "/")


def _raison_ignoree(rel, jekyll=True):
    """Pourquoi ce HTML n'a pas à être dans le sitemap (None = c'est une vraie page).
    Tout dossier est publié par GitHub Pages (assets/, data/, scripts/ compris), sauf
    les dossiers « . » et, tant que Jekyll est actif (pas de .nojekyll), les dossiers « _ »."""
    comps = rel.split("/")
    if rel == "404.html":
        return "page d'erreur, servie avec le code 404"
    if re.fullmatch(r"google[0-9a-f]{8,}\.html", rel):  # racine seulement, hexadécimal
        return "fichier de validation Google"
    for c in comps[:-1]:
        if c.startswith(".") or (jekyll and c.startswith("_")):
            return "dossier %s non publié" % c
    return None


class _GitDates:
    """Date (AAAA-MM-JJ) du dernier commit d'un fichier ; None si git indisponible."""

    def __init__(self, racine, rev=None):
        self.racine, self.rev, self.ok = racine, rev, True

    def date(self, rel):
        if not self.ok:
            return None
        try:
            r = subprocess.run(["git", "log", "-1", "--format=%cd", "--date=short"] +
                               ([self.rev] if self.rev else []) + ["--", rel],
                               cwd=self.racine, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            self.ok = False
            return None
        s = (r.stdout or "").strip()
        if r.returncode != 0:
            self.ok = False
            return None
        return s if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else None


def _section(titre_ok, bloquants=None, alertes=None, infos=None):
    return {"ok": titre_ok, "bloquants": bloquants or [], "alertes": alertes or [],
            "infos": infos or []}


def _controle_sitemap(racine):
    """Renvoie (section, entrées [(loc, lastmod, rel_fichier)])."""
    B, A = [], []
    chemin = os.path.join(racine, "sitemap.xml")
    if not os.path.isfile(chemin):
        return _section("sitemap.xml", ["sitemap.xml introuvable à la racine du dépôt."]), []
    try:
        racine_xml = ET.parse(chemin).getroot()
    except ET.ParseError as e:
        return _section("sitemap.xml", ["sitemap.xml illisible (XML cassé) : %s" % e]), []
    if racine_xml.tag != NS + "urlset":
        return _section("sitemap.xml", ["sitemap.xml : balise racine %s au lieu de <urlset> "
                                        "(espace de noms sitemaps.org 0.9)." % racine_xml.tag]), []
    entrees, vus = [], {}
    aujourdhui = datetime.date.today().isoformat()
    for enfant in racine_xml:
        if enfant.tag != NS + "url":
            B.append("sitemap.xml : balise inattendue %s dans <urlset> (seules les <url> "
                     "sont permises)." % enfant.tag)
    for i, u in enumerate(racine_xml.findall(NS + "url"), 1):
        e_loc, e_mod = u.find(NS + "loc"), u.find(NS + "lastmod")
        loc = (e_loc.text or "").strip() if e_loc is not None else ""
        if not loc:
            B.append("sitemap.xml : l'entrée n°%d n'a pas de <loc>." % i)
            continue
        cle = unquote(loc)
        if cle in vus:
            n0, loc0 = vus[cle]
            B.append("sitemap.xml : %s est en double (entrées n°%d « %s » et n°%d « %s »)."
                     % (cle, n0, loc0, i, loc))
            continue
        vus[cle] = (i, loc)
        if not loc.startswith(BASE):
            B.append("sitemap.xml : %s ne commence pas par %s" % (loc, BASE))
            continue
        if not loc.endswith("/"):
            B.append("sitemap.xml : %s doit finir par « / »." % loc)
            continue
        if "?" in loc or "#" in loc:
            B.append("sitemap.xml : %s contient « ? » ou « # »." % loc)
            continue
        rel, souci = _fichier_de_loc(racine, loc)
        if souci:
            B.append("sitemap.xml : %s -> %s" % (loc, souci))
            rel = None
        mod = (e_mod.text or "").strip() if e_mod is not None else ""
        if e_mod is None:
            A.append("sitemap.xml : %s n'a pas de <lastmod> (conseillé)." % loc)
        elif not mod:
            B.append("sitemap.xml : %s a un <lastmod> vide." % loc)
        else:
            if not _lastmod_valide(mod):
                B.append("sitemap.xml : %s a un lastmod « %s » (attendu AAAA-MM-JJ)." % (loc, mod))
                mod = ""
            elif mod[:10] > aujourdhui:
                A.append("sitemap.xml : %s a un lastmod dans le futur (%s)." % (loc, mod))
        entrees.append((loc, mod[:10] if len(mod) >= 10 else "", rel))
    if not vus:
        B.append("sitemap.xml ne contient aucune adresse.")
    for p in PAGES_ATTENDUES:
        if p not in vus:
            B.append("sitemap.xml : la page %s a disparu du sitemap. Si c'est voulu, retire-la "
                     "aussi de PAGES_ATTENDUES (scripts/check_seo.py) dans le même commit." % p)
    return _section("sitemap.xml (%d adresses) : en %s…/, sans doublon, fichier présent, "
                    "lastmod AAAA-MM-JJ" % (len(entrees), BASE), B, A), entrees


_RE_W3C = re.compile(r"\d{4}(-\d{2}(-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2}))?)?)?")


def _lastmod_valide(mod):
    """Format W3C Datetime (celui du protocole sitemap) et date réelle."""
    if not _RE_W3C.fullmatch(mod):
        return False
    try:
        a = int(mod[:4])
        m = int(mod[5:7]) if len(mod) >= 7 else 1
        j = int(mod[8:10]) if len(mod) >= 10 else 1
        datetime.date(a, m, j)
        if len(mod) > 10:
            h, mi = int(mod[11:13]), int(mod[14:16])
            if h > 23 or mi > 59:
                return False
    except ValueError:
        return False
    return True


_RE_HOTE_MAISON = re.compile(
    r"(?i)(https?:)?//((?:[a-z0-9-]+\.)*thejammerz\.com)(?![a-z0-9.-]*[a-z0-9])")


def _url_norm(url):
    """Forme comparable d'une URL : schéma et hôte en minuscules, port par défaut retiré."""
    try:
        p = urlsplit((url or "").strip())
        port = p.port
    except ValueError:
        return url
    hote = (p.hostname or "").lower()
    if port and not (p.scheme.lower(), port) in (("https", 443), ("http", 80)):
        hote += ":%d" % port
    return "%s://%s%s%s%s" % (p.scheme.lower(), hote, p.path or "/",
                              "?" + p.query if p.query else "",
                              "#" + p.fragment if p.fragment else "")


def _controle_page_sitemap(racine, loc, rel):
    """Contrôles bloquants d'une page listée dans le sitemap. Renvoie (bloquants, alertes)."""
    B, A = [], []
    texte = _lire(os.path.join(racine, rel))
    try:
        a = _analyser(texte)
    except Exception as e:  # HTML vraiment cassé
        return ["%s : HTML illisible (%s)." % (rel, e)], []

    # 1 seule canonique, DANS le <head>, identique à l'adresse du sitemap
    for h in a.canon_hors_head:
        B.append("%s : balise canonical « %s » dans le <body> : Google l'ignore. Elle doit "
                 "être dans le <head>." % (rel, h))
    if len(a.canoniques) != 1:
        B.append("%s : %d balise(s) canonical au lieu d'une seule." % (rel, len(a.canoniques)))
    elif a.canoniques[0] != loc:
        if _url_norm(a.canoniques[0]) == _url_norm(loc):
            A.append("%s : canonique « %s » équivalente mais pas écrite exactement comme « %s »."
                     % (rel, a.canoniques[0], loc))
        else:
            B.append("%s : canonique « %s », attendu « %s »." % (rel, a.canoniques[0], loc))
    for r in a.refresh:
        B.append("%s : balise <meta http-equiv=\"refresh\" content=\"%s\"> : une page du "
                 "sitemap ne doit pas rediriger." % (rel, r))

    # (le noindex d'une page du sitemap est contrôlé dans verifier_hors_ligne,
    #  section « pages noindex », pour ne pas le signaler deux fois)

    # zéro thejammerz.github.io, où que ce soit, même camouflé (&#46;, \/, %2E...)
    lignes = _lignes_ancien(texte)
    if lignes:
        B.append("%s : contient « github.io » (ligne%s %s)." % (
            rel, "s" if len(lignes) > 1 else "", ", ".join(map(str, lignes[:5]))))

    # auto-références absolues : https://thejammerz.com uniquement
    refs = [("canonical", h) for h in a.canoniques + a.canon_hors_head] + \
        [("og:url", h) for h in a.og_url] + [("hreflang", h) for h in a.hreflang] + \
        [("base", h) for h in a.bases]
    for n, bloc in enumerate(a.ld_blocs, 1):
        try:
            donnees = json.loads(bloc)
        except ValueError as e:
            A.append("%s : bloc JSON-LD n°%d illisible (%s) : Google l'ignorera." % (rel, n, e))
            continue
        refs += [("JSON-LD", u) for u in _urls_jsonld(donnees)]
        for page in _pages_jsonld(donnees):
            if page["url"].strip() != loc and not _souci_hote(page["url"]):
                B.append("%s : JSON-LD %s « url » = « %s », attendu « %s »."
                         % (rel, page.get("@type"), page["url"], loc))
    for n, s in enumerate(a.scripts, 1):
        if re.search(r"(?i)noindex", s):
            B.append("%s : un script de la page contient « noindex » (balise robots ajoutée "
                     "par JavaScript ?). Google exécute le JS : la page sortirait de l'index."
                     % rel)
            break
    deja = set()  # débuts d'adresse fautifs déjà signalés (évite les doublons)
    for genre, url in refs:
        souci = _souci_hote(url)
        if souci:
            m = _RE_HOTE_MAISON.search(url)
            if m:
                deja.add(((m.group(1) or "") + "//" + m.group(2)).lower())
            if souci != "ancienne adresse github.io":  # github.io déjà signalé plus haut
                B.append("%s : %s « %s » -> %s." % (rel, genre, url, souci))
    for og in a.og_url:
        if _souci_hote(og):
            continue  # déjà signalé
        if not (og + "/").startswith(BASE):
            B.append("%s : og:url « %s » doit être une adresse complète %s…" % (rel, og, BASE))
        elif og != loc:
            # même page à la barre finale près = simple alerte (og:url ne fixe pas la canonique)
            (A if _url_norm(og).rstrip("/") == _url_norm(loc).rstrip("/") else B).append(
                "%s : og:url « %s » différent de l'adresse de la page (%s)." % (rel, og, loc))

    # partout ailleurs dans le fichier : pas de http:// ni www. vers le site
    for m in _RE_HOTE_MAISON.finditer(_normaliser(texte)):
        url = (m.group(1) or "") + "//" + m.group(2)
        souci = _souci_hote(url + "/")
        if souci and url.lower() not in deja:
            deja.add(url.lower())
            ligne = texte.count("\n", 0, m.start()) + 1
            B.append("%s : lien « %s… » ligne %d -> %s." % (rel, url, ligne, souci))
    return B, A


# Hôte insensible à la casse, CHEMIN sensible (GitHub Pages distingue /Zones/ de /zones/).
_RE_HREF_ZONES = re.compile(
    r"""(?i:href)\s*=\s*\\?["']?(?:(?i:(?:https?:)?//(?:www\.)?thejammerz\.(?:com|github\.io)))?"""
    r"""(?:\.?/)?zones(?:[/"'\s>#?\\]|$)""")


# Redirection JS vers /zones/ : location = …, location.href = …, location.assign/replace(…).
_RE_JS_ZONES = re.compile(
    r"""location(?:\.href)?\s*(?:=|\.(?:assign|replace)\s*\()\s*["'`]"""
    r"""(?:(?i:(?:https?:)?//(?:www\.)?thejammerz\.(?:com|github\.io)))?/zones(?:[/"'`?#]|$)""")


def _vise_zones(href, base=BASE):
    u = urljoin(base, (href or "").strip())
    try:
        p = urlsplit(u)
    except ValueError:
        return False
    hote = (p.hostname or "").lower()
    return hote in HOTES_MAISON and (p.path == "/zones" or p.path.startswith("/zones/"))


def _controle_accueil(racine):
    B = []
    chemin = os.path.join(racine, "index.html")
    if not os.path.isfile(chemin):
        return _section("accueil", ["index.html (l'accueil) introuvable."])
    texte = _lire(chemin)
    a = _analyser(texte)
    if VERIF_GOOGLE not in a.verif:
        B.append("index.html : la balise google-site-verification (%s) a disparu ou a changé "
                 "(trouvé : %s). Search Console perdrait la propriété." % (
                     VERIF_GOOGLE, ", ".join(a.verif) or "rien"))
    # liens HTML vus par l'analyseur ; à défaut, repli texte brut (href dans du JS, etc.)
    base = urljoin(BASE, a.bases[0].strip()) if a.bases else BASE
    brut = _normaliser(_sans_commentaires(texte))  # un lien en commentaire HTML ne compte pas
    liens = sorted({h for h in a.hrefs if _vise_zones(h, base)}) or \
        sorted({m.group(0) for m in _RE_HREF_ZONES.finditer(brut)}) or \
        sorted({m.group(0) for m in _RE_JS_ZONES.finditer(brut)})
    if liens:
        B.append("index.html : contient un lien vers /zones/ (%s). L'accueil est intouchable : "
                 "ce lien ne doit pas y être." % " | ".join(liens[:5]))
    return _section("accueil (index.html) : balise Google présente, pas de lien vers /zones/", B)


# Fautes de frappe que Google accepte quand même (cf. son analyseur open source).
_CLES_UA = {"user-agent", "useragent", "user agent"}
_CLES_DISALLOW = {"disallow", "dissallow", "dissalow", "disalow", "diasllow", "disallaw"}
_CLES_SITEMAP = {"sitemap", "site-map"}


def _lire_robots(texte):
    """Lit robots.txt comme Googlebot. Renvoie (règles [(n°, type, chemin)] qui
    s'appliquent à Googlebot, [urls Sitemap])."""
    groupes, agents, regles, en_regles, sitemaps = [], [], [], False, []
    for n, ligne in enumerate(texte.splitlines(), 1):
        l = ligne.split("#", 1)[0].strip()
        if not l:
            continue
        if ":" in l:
            cle, _, val = l.partition(":")
        else:  # « Disallow /x » sans deux-points : Google l'accepte s'il y a 2 mots
            morceaux = l.split()
            if len(morceaux) != 2:
                continue
            cle, val = morceaux
        cle, val = cle.strip().lower(), val.strip()
        if cle in _CLES_UA:
            if en_regles:  # seules les règles referment un groupe
                groupes.append((agents, regles))
                agents, regles, en_regles = [], [], False
            jeton = "*" if val.startswith("*") else re.match(r"[A-Za-z_-]*", val).group(0).lower()
            agents.append(jeton)
        elif cle == "allow" or cle in _CLES_DISALLOW:
            en_regles = True
            regles.append((n, "allow" if cle == "allow" else "disallow", val))
        elif cle in _CLES_SITEMAP:
            sitemaps.append(val)
    groupes.append((agents, regles))
    pour_google = [r for ag, rg in groupes if "googlebot" in ag for r in rg]
    if not any("googlebot" in ag for ag, _ in groupes):
        pour_google = [r for ag, rg in groupes if "*" in ag for r in rg]
    return pour_google, sitemaps


def _regle_gagnante(regles, chemin):
    """Règle qui décide pour ce chemin : la plus longue gagne, Allow gagne l'égalité."""
    meilleure = None
    for n, typ, val in regles:
        if not val:
            continue
        fin = val.endswith("$")
        motif = "".join(".*" if c == "*" else re.escape(c) for c in (val[:-1] if fin else val))
        if re.match(motif + ("$" if fin else ""), chemin):
            cle = (len(val), typ == "allow")
            if meilleure is None or cle > meilleure[0]:
                meilleure = (cle, n, typ, val)
    return meilleure


def _controle_robots(racine, locs=()):
    B, A = [], []
    chemin = os.path.join(racine, "robots.txt")
    if not os.path.isfile(chemin):
        return _section("robots.txt", ["robots.txt introuvable à la racine."])
    with open(chemin, "rb") as f:
        brut = f.read()
    if brut[:2] in (b"\xff\xfe", b"\xfe\xff"):
        B.append("robots.txt est encodé en UTF-16 : Google ne le lit pas correctement. "
                 "Réenregistre-le en UTF-8.")
        texte = brut.decode("utf-16", "replace")
    else:
        if b"\x00" in brut:
            B.append("robots.txt contient des caractères nuls (fichier abîmé ou mal encodé).")
        texte = brut.decode("utf-8-sig", "replace")
    regles, sitemaps = _lire_robots(texte)
    chemins = sorted({urlsplit(l).path or "/" for l in locs} | {"/", "/sitemap.xml"})
    for c in chemins:
        g = _regle_gagnante(regles, c)
        if g and g[2] == "disallow":
            B.append("robots.txt ligne %d : « Disallow: %s » (pour %s) bloque %s."
                     % (g[1], g[3], "Googlebot", c))
    if SITEMAP_URL not in sitemaps:
        B.append("robots.txt : la ligne « Sitemap: %s » manque (trouvé : %s)."
                 % (SITEMAP_URL, ", ".join(sitemaps) or "aucune"))
    return _section("robots.txt : aucune page du sitemap interdite à Googlebot, ligne Sitemap "
                    "présente", B, A)


def _controle_cname(racine):
    chemin = os.path.join(racine, "CNAME")
    if not os.path.isfile(chemin):
        return _section("CNAME", ["Fichier CNAME absent : GitHub Pages perdrait le domaine %s."
                                  % DOMAINE])
    with open(chemin, "rb") as f:
        brut = f.read()
    A = ["CNAME commence par un BOM (caractère invisible) : à retirer."] \
        if brut.startswith(b"\xef\xbb\xbf") else []
    contenu = brut.decode("utf-8-sig", "replace").strip()
    if contenu.lower() != DOMAINE:
        return _section("CNAME", ["CNAME contient « %s » au lieu de « %s »." % (contenu, DOMAINE)])
    return _section("CNAME = %s" % DOMAINE, alertes=A)


def verifier_hors_ligne(racine=RACINE_DEFAUT, depot=None, rev=None):
    """Tous les contrôles sur les fichiers du dépôt. Renvoie une liste de sections
    {"ok": libellé, "bloquants": [...], "alertes": [...], "infos": [...]}.
    depot/rev : dépôt git et commit d'où vient « racine » (mode --commit)."""
    sections = []
    s_sitemap, entrees = _controle_sitemap(racine)
    sections.append(s_sitemap)
    locs = {loc for loc, _, _ in entrees}

    # pages du sitemap
    B, A = [], []
    dates = _GitDates(depot or racine, rev)
    pages = [(loc, mod, rel) for loc, mod, rel in entrees if rel]
    for loc, mod, rel in pages:
        b, a = _controle_page_sitemap(racine, loc, rel)
        B += b
        A += a
        if mod:
            d = dates.date(rel)
            if d and mod < d:
                A.append("sitemap.xml : lastmod de %s = %s, plus ancien que le dernier commit "
                         "de %s (%s)." % (loc, mod, rel, d))
    sections.append(_section("pages du sitemap (%d) : une seule canonique = son adresse, zéro "
                             "github.io, liens vers le site en https://%s" % (len(pages), DOMAINE),
                             B, A))

    # tous les HTML du dépôt : noindex hors sitemap + pages indexables oubliées
    B_noindex, noindex, B_orph, A_orph, ignores = [], [], [], [], []
    jekyll = not os.path.exists(os.path.join(racine, ".nojekyll"))
    for rel in _tous_les_html(racine):
        url = _url_de_fichier(rel)
        try:
            robots = _analyser(_lire(os.path.join(racine, rel))).robots
        except Exception as e:
            B_orph.append("%s : HTML illisible (%s)." % (rel, e))
            continue
        raison = _raison_ignoree(rel, jekyll)
        if raison:
            ignores.append("%s (%s)" % (rel, raison))
        if _dit_noindex(robots):
            noindex.append(rel)
            if url in locs:
                B_noindex.append("%s porte noindex (%s) mais %s est dans le sitemap : Google "
                                 "reçoit deux ordres contraires. Retire-la du sitemap ou enlève "
                                 "le noindex." % (rel, " | ".join(robots), url))
            elif rel not in NOINDEX_AUTORISES and not raison and                     rel.split("/", 1)[0] not in DOSSIERS_ANNEXES:
                B_noindex.append("%s porte noindex (%s) : seules %s y ont droit. Si c'est voulu, "
                                 "ajoute-la à NOINDEX_AUTORISES (scripts/check_seo.py)."
                                 % (rel, " | ".join(robots), ", ".join(NOINDEX_AUTORISES)))
        elif not raison and url not in locs:
            (A_orph if "/" in rel and rel.split("/", 1)[0] in DOSSIERS_ANNEXES else B_orph).append("%s : page indexable (%s) absente du sitemap. Ajoute-la au sitemap "
                          "ou mets-lui un noindex si elle ne doit pas sortir sur Google."
                          % (rel, url))
    if jekyll:
        for rel in _tous_les_fichiers(racine):
            if rel.lower().endswith(".md") and not _raison_ignoree(rel) and \
                    not re.fullmatch(r"(?i)(readme|license|licence|contributing|changelog)\.md",
                                     rel.rsplit("/", 1)[-1]):
                B_orph.append("%s : Jekyll le publiera comme une page (%s). Ajoute-le au "
                              "sitemap ou supprime-le." % (rel, _url_de_fichier(rel[:-3] + ".html")))
    hors = [r for r in noindex if _url_de_fichier(r) not in locs]
    sections.append(_section("aucune page noindex dans le sitemap (noindex voulu, hors sitemap : "
                             "%s)" % (", ".join(hors) or "aucune"), B_noindex))
    sections.append(_section("aucune page indexable oubliée du sitemap", B_orph, A_orph,
                             infos=["ignorés : " + " ; ".join(ignores)] if ignores else []))

    sections.append(_controle_accueil(racine))
    sections.append(_controle_robots(racine, locs))
    sections.append(_controle_cname(racine))

    # l'ancienne adresse dans N'IMPORTE QUEL fichier publié (hors pages du sitemap, déjà vues)
    B_anc = []
    deja_vus = {rel for _, _, rel in entrees if rel}
    for rel in _tous_les_fichiers(racine):
        comps = rel.split("/")
        if rel in deja_vus or not rel.lower().endswith(_EXT_TEXTE) or \
                any(c.startswith((".", "_")) for c in comps[:-1]) or comps[0] == "scripts":
            continue
        lignes = _lignes_ancien(_lire(os.path.join(racine, rel)),
                                rel.lower().endswith((".html", ".htm", ".svg")))
        if lignes:
            B_anc.append("%s : contient « %s » (ligne%s %s). Remplace par %s."
                         % (rel, ANCIEN, "s" if len(lignes) > 1 else "",
                            ", ".join(map(str, lignes[:5])), BASE))
    sections.append(_section("aucun fichier publié ne mentionne %s" % ANCIEN, B_anc))
    return sections


def _tous_les_fichiers(racine):
    for dossier, sous, noms in os.walk(racine):
        sous[:] = sorted(d for d in sous if d not in DOSSIERS_JAMAIS)
        for n in sorted(noms):
            yield os.path.relpath(os.path.join(dossier, n), racine).replace(os.sep, "/")


def _extraire_commit(depot, rev):
    """Contenu EXACT du commit rev (git archive) dans un dossier temporaire."""
    r = subprocess.run(["git", "archive", "--format=tar", rev], cwd=depot,
                       capture_output=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError("git archive %s a échoué : %s"
                           % (rev, r.stderr.decode("utf-8", "replace").strip()))
    tmp = tempfile.mkdtemp(prefix="check_seo_")
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as t:
        membres = [m for m in t.getmembers() if m.isfile() or m.isdir()]
        try:
            t.extractall(tmp, members=membres, filter="data")
        except TypeError:  # Python < 3.12
            t.extractall(tmp, members=membres)
    return tmp


def _main_hors_ligne(racine, depot=None, rev=None):
    print("Contrôle SEO The Jammerz — hors ligne (fichiers du dépôt)")
    if rev:
        print("  (contenu exact du commit %s)" % rev)
    sections = verifier_hors_ligne(racine, depot, rev)
    nb_b = nb_a = 0
    for s in sections:
        print("  %s  %s" % ("OK" if not s["bloquants"] else "KO", s["ok"]))
        for m in s["bloquants"]:
            print("      BLOQUANT : " + m)
        for m in s["alertes"]:
            print("      attention (non bloquant) : " + m)
        for m in s["infos"]:
            print("      " + m)
        nb_b += len(s["bloquants"])
        nb_a += len(s["alertes"])
    if nb_b:
        print("Résultat : ÉCHEC — %d problème(s) bloquant(s). À corriger avant de pousser." % nb_b)
        return 1
    print("Résultat : OK — rien de bloquant%s." % (
        " (%d point(s) d'attention)" % nb_a if nb_a else ""))
    return 0


# --------------------------------------------------------------------------
# MODE EN LIGNE
# --------------------------------------------------------------------------
def _requete(url, timeout=20, lire=True):
    """GET SANS suivre les redirections (on regarde la 1re réponse).
    Un essai de plus après 2 s en cas d'erreur réseau. Ne lève jamais d'exception.
    Renvoie {"statut", "entetes" (clés en minuscules -> liste), "corps" (bytes), "erreur"}."""
    erreur = "?"
    for essai in (1, 2):
        conn = None
        try:
            p = urlsplit(url)
            if p.scheme == "https":
                conn = http.client.HTTPSConnection(p.hostname, p.port or 443, timeout=timeout,
                                                   context=ssl.create_default_context())
            else:
                conn = http.client.HTTPConnection(p.hostname, p.port or 80, timeout=timeout)
            chemin = (p.path or "/") + ("?" + p.query if p.query else "")
            conn.request("GET", chemin, headers={
                "User-Agent": UA, "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "identity", "Connection": "close"})
            rep = conn.getresponse()
            corps = rep.read(5_000_000) if lire else b""
            entetes = {}
            for k, v in rep.getheaders():
                entetes.setdefault(k.lower(), []).append(v)
            return {"statut": rep.status, "entetes": entetes, "corps": corps, "erreur": None}
        except Exception as e:  # réseau, TLS, DNS, délai... -> devient un problème
            erreur = "%s: %s" % (type(e).__name__, e)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        if essai == 1:
            time.sleep(2)
    return {"statut": None, "entetes": {}, "corps": b"", "erreur": erreur}


def _entete(r, nom):
    v = r["entetes"].get(nom.lower(), [])
    return v[0] if v else ""


def _locs_du_xml(corps):
    racine = ET.fromstring(corps)
    return [(u.findtext(NS + "loc") or "").strip() for u in racine.findall(NS + "url")]


def _verif_page(loc, timeout):
    chemin = urlsplit(loc).path or "/"
    r = _requete(loc, timeout)
    if r["erreur"]:
        return [_pb("page:%s:injoignable" % chemin, "panne", "Page %s injoignable" % chemin,
                    "Pas de réponse de %s (%s)." % (loc, r["erreur"]))]
    if r["statut"] != 200:
        ou = _entete(r, "location")
        return [_pb("page:%s:statut" % chemin, "panne",
                    "Page %s : code %s au lieu de 200" % (chemin, r["statut"]),
                    "%s répond %s%s. Attendu : 200 sans redirection." % (
                        loc, r["statut"], " et renvoie vers %s" % ou if ou else ""))]
    pbs = []
    xrt = r["entetes"].get("x-robots-tag", [])
    if _dit_noindex(xrt):
        pbs.append(_pb("page:%s:x-robots-tag" % chemin, "panne",
                       "Page %s interdite à Google (en-tête)" % chemin,
                       "%s renvoie l'en-tête X-Robots-Tag : %s." % (loc, " | ".join(xrt))))
    html = r["corps"].decode("utf-8", "replace")
    try:
        a = _analyser(html)
    except Exception as e:
        return pbs + [_pb("page:%s:html" % chemin, "panne", "Page %s illisible" % chemin,
                          "HTML servi par %s illisible (%s)." % (loc, e))]
    if len(a.canoniques) != 1 or a.canoniques[0] != loc:
        pbs.append(_pb("page:%s:canonical" % chemin, "panne",
                       "Page %s : mauvaise canonique" % chemin,
                       "Canonique servie : %s ; attendu exactement %s." % (
                           " | ".join(a.canoniques) or "aucune", loc)))
    if _dit_noindex(a.robots):
        pbs.append(_pb("page:%s:noindex" % chemin, "panne",
                       "Page %s interdite à Google (noindex)" % chemin,
                       "%s porte <meta robots> « %s » alors qu'elle est dans le sitemap." % (
                           loc, " | ".join(a.robots))))
    lignes = _lignes_ancien(html)
    if lignes:
        pbs.append(_pb("page:%s:github.io" % chemin, "panne",
                       "Page %s mentionne encore github.io" % chemin,
                       "Le HTML servi par %s contient « github.io » (ligne(s) %s)." % (
                           loc, ", ".join(map(str, lignes[:5])))))
    return pbs


def _verif_redirection(url, attendu, key, timeout):
    r = _requete(url, timeout, lire=False)
    if r["erreur"]:
        return [_pb(key, "panne", "%s injoignable" % url,
                    "Pas de réponse de %s (%s). Attendu : 301 vers %s." % (url, r["erreur"], attendu))]
    ou = _entete(r, "location")
    if r["statut"] != 301:
        return [_pb(key, "panne", "%s : code %s au lieu de 301" % (url, r["statut"]),
                    "%s répond %s%s. Attendu : 301 vers %s." % (
                        url, r["statut"], " (vers %s)" % ou if ou else "", attendu))]
    if ou != attendu:
        return [_pb(key, "panne", "%s redirige au mauvais endroit" % url,
                    "%s renvoie (301) vers « %s » au lieu de « %s »." % (url, ou, attendu))]
    return []


def _verif_404(timeout):
    chemin = "/controle-seo-%s/" % secrets.token_hex(6)
    url = BASE + chemin[1:]
    r = _requete(url, timeout, lire=False)
    if r["erreur"]:
        return [_pb("404:injoignable", "surveil", "Test 404 impossible",
                    "Pas de réponse de %s (%s)." % (url, r["erreur"]))]
    if r["statut"] != 404:
        return [_pb("404:statut", "surveil", "Adresse inconnue : code %s au lieu de 404" % r["statut"],
                    "%s (adresse qui n'existe pas) répond %s. Attendu : 404, sinon Google peut "
                    "indexer des pages vides." % (url, r["statut"]))]
    return []


def _verif_page_noindex(chemin, timeout):
    url = BASE + chemin.lstrip("/")
    r = _requete(url, timeout)
    if r["erreur"]:
        return [_pb("noindex:%s:injoignable" % chemin, "surveil", "Page %s injoignable" % chemin,
                    "Pas de réponse de %s (%s)." % (url, r["erreur"]))]
    if r["statut"] != 200:
        return [_pb("noindex:%s:statut" % chemin, "surveil",
                    "Page %s : code %s au lieu de 200" % (chemin, r["statut"]),
                    "%s répond %s. Cette page légale doit rester en ligne (en noindex)." % (
                        url, r["statut"]))]
    try:
        robots = _analyser(r["corps"].decode("utf-8", "replace")).robots
    except Exception:
        robots = []
    if not (_dit_noindex(robots) or _dit_noindex(r["entetes"].get("x-robots-tag", []))):
        return [_pb("noindex:%s:indexable" % chemin, "surveil",
                    "Page %s devenue indexable" % chemin,
                    "%s ne porte plus de noindex (meta robots : %s). Elle était volontairement "
                    "hors de Google : vérifier si c'est voulu." % (url, " | ".join(robots) or "aucune"))]
    return []


REDIRECTIONS = (
    [("redir:github.io:%s" % p, "https://%s%s" % (ANCIEN, p), BASE + p.lstrip("/"))
     for p in ("/", "/zones/", "/zones/anglet/", "/zones/biarritz/")] +
    [("redir:http", "http://%s/" % DOMAINE, BASE),
     ("redir:www", "https://www.%s/" % DOMAINE, BASE)])
PAGES_NOINDEX = tuple("/" + r[:-len("index.html")] for r in NOINDEX_AUTORISES
                      if r.endswith("/index.html"))


def _live_groupes(timeout=20):
    """Lance tous les contrôles en ligne. Renvoie [(libellé OK, [problèmes])]."""
    groupes = []

    def protege(nom, fonction, *args):
        try:
            return fonction(*args)
        except Exception as e:  # ceinture + bretelles : jamais de plantage
            return [_pb("controle:%s" % nom, "surveil", "Contrôle « %s » en erreur" % nom,
                        "Le contrôle a planté (%s: %s)." % (type(e).__name__, e))]

    # 1. sitemap en ligne
    pbs_sm, locs, site_mort = [], None, False
    r = _requete(SITEMAP_URL, timeout)
    if r["erreur"]:
        site_mort = True
        pbs_sm.append(_pb("site:injoignable", "panne", "Site thejammerz.com injoignable",
                          "Pas de réponse de %s (%s)." % (SITEMAP_URL, r["erreur"])))
    elif r["statut"] != 200:
        pbs_sm.append(_pb("sitemap:statut", "panne", "Sitemap en ligne : code %s" % r["statut"],
                          "%s répond %s au lieu de 200." % (SITEMAP_URL, r["statut"])))
    else:
        try:
            locs = _locs_du_xml(r["corps"])
        except ET.ParseError as e:
            pbs_sm.append(_pb("sitemap:illisible", "panne", "Sitemap en ligne illisible",
                              "%s n'est pas un XML valide (%s)." % (SITEMAP_URL, e)))
        else:
            mauvaises = [l for l in locs if not (l.startswith(BASE) and l.endswith("/"))]
            if mauvaises:
                pbs_sm.append(_pb("sitemap:adresses", "panne", "Sitemap en ligne : adresses non conformes",
                                  "Adresses hors %s…/ : %s" % (BASE, ", ".join(mauvaises[:5]))))
            if not locs:
                pbs_sm.append(_pb("sitemap:vide", "panne", "Sitemap en ligne vide",
                                  "%s ne liste aucune adresse." % SITEMAP_URL))
            manquantes = [p for p in PAGES_ATTENDUES if p not in set(map(unquote, locs))]
            if locs and manquantes:
                pbs_sm.append(_pb("sitemap:manquantes", "panne",
                                  "Sitemap en ligne : %d page(s) attendue(s) absente(s)"
                                  % len(manquantes),
                                  "Absentes de %s : %s" % (SITEMAP_URL, ", ".join(manquantes[:8]))))
    if locs is None and not site_mort:  # repli : le sitemap du dépôt, s'il est là
        try:
            with open(os.path.join(RACINE_DEFAUT, "sitemap.xml"), "rb") as f:
                locs = _locs_du_xml(f.read())
            for p in pbs_sm:
                p["detail"] += " Pages contrôlées d'après le sitemap du dépôt local."
        except Exception:
            locs = None
    groupes.append(("sitemap en ligne lu : %d adresses" % len(locs or []), pbs_sm))

    with ThreadPoolExecutor(max_workers=8) as pool:
        f_pages = [pool.submit(protege, "page " + l, _verif_page, l, timeout)
                   for l in (locs or []) if l.startswith(BASE)]
        f_redir = [(k, pool.submit(protege, k, _verif_redirection, u, att, k, timeout))
                   for k, u, att in REDIRECTIONS]
        f_404 = pool.submit(protege, "404", _verif_404, timeout)
        f_noidx = [pool.submit(protege, "noindex " + c, _verif_page_noindex, c, timeout)
                   for c in PAGES_NOINDEX]

        if locs is not None:
            groupes.append(("%d pages du sitemap : 200 sans redirection, canonique exacte, pas de "
                            "noindex (meta ni en-tête), zéro github.io" % len(f_pages),
                            [p for f in f_pages for p in f.result()]))
        redir = [(k, f.result()) for k, f in f_redir]
        groupes.append(("ancienne adresse %s -> 301 vers la même page sur %s (/, /zones/, "
                        "/zones/anglet/, /zones/biarritz/)" % (ANCIEN, DOMAINE),
                        [p for k, pbs in redir if k.startswith("redir:github.io") for p in pbs]))
        groupes.append(("http://%s/ et https://www.%s/ -> 301 vers %s" % (DOMAINE, DOMAINE, BASE),
                        [p for k, pbs in redir if not k.startswith("redir:github.io") for p in pbs]))
        groupes.append(("adresse inconnue -> 404", f_404.result()))
        groupes.append(("%s : en ligne (200) et toujours en noindex (voulu)"
                        % " et ".join(PAGES_NOINDEX), [p for f in f_noidx for p in f.result()]))
    return groupes


def live_problems(timeout=20):
    """Contrôle EN LIGNE du site. Renvoie la liste des problèmes (vide = tout va bien) :
    [{"key": str, "level": "panne"|"surveil", "titre": str, "detail": str}, ...].
    Ne lève jamais d'exception : une erreur réseau devient un problème."""
    try:
        return [p for _, pbs in _live_groupes(timeout) for p in pbs]
    except Exception as e:
        return [_pb("controle:erreur", "surveil", "Contrôle SEO en ligne en erreur",
                    "Le contrôle a planté (%s: %s)." % (type(e).__name__, e))]


def _main_live(timeout):
    print("Contrôle SEO The Jammerz — en ligne (%s)" % BASE)
    try:
        groupes = _live_groupes(timeout)
    except Exception as e:
        groupes = [("contrôle en ligne", [_pb("controle:erreur", "surveil", "Contrôle en erreur",
                                              "%s: %s" % (type(e).__name__, e))])]
    nb_p = nb_s = 0
    for libelle, pbs in groupes:
        print("  %s  %s" % ("OK" if not pbs else "KO", libelle))
        for p in pbs:
            print("      %s : %s — %s" % ("PANNE" if p["level"] == "panne" else "à surveiller",
                                          p["titre"], p["detail"]))
            if p["level"] == "panne":
                nb_p += 1
            else:
                nb_s += 1
    if nb_p:
        print("Résultat : ÉCHEC — %d panne(s)%s." % (nb_p, ", %d point(s) à surveiller" % nb_s if nb_s else ""))
        return 1
    print("Résultat : OK — aucune panne%s." % (
        " (%d point(s) à surveiller)" % nb_s if nb_s else ", rien à surveiller"))
    return 0


# --------------------------------------------------------------------------
def main(argv=None):
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Garde-fou SEO du site The Jammerz.")
    ap.add_argument("--live", action="store_true", help="contrôle le site en ligne")
    ap.add_argument("--json", action="store_true",
                    help="contrôle en ligne, sortie JSON (liste des problèmes)")
    ap.add_argument("--timeout", type=float, default=20, help="délai réseau en secondes")
    ap.add_argument("--racine", default=RACINE_DEFAUT, help="dossier du dépôt (hors ligne)")
    ap.add_argument("--commit", help="contrôle hors ligne du contenu exact de ce commit")
    args = ap.parse_args(argv)
    try:
        if args.json:
            pbs = live_problems(args.timeout)
            print(json.dumps(pbs, ensure_ascii=False, indent=2))
            return 1 if any(p["level"] == "panne" for p in pbs) else 0
        if args.live:
            return _main_live(args.timeout)
        depot = os.path.abspath(args.racine)
        if args.commit:
            tmp = _extraire_commit(depot, args.commit)
            try:
                return _main_hors_ligne(tmp, depot, args.commit)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        return _main_hors_ligne(depot)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print("ERREUR du contrôle SEO lui-même : %s: %s" % (type(e).__name__, e))
        print("Par sécurité, cela compte comme un échec.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
