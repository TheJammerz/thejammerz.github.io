# -*- coding: utf-8 -*-
"""Bascule le site de thejammerz.github.io vers un domaine perso (ex. thejammerz.com).

A LANCER SEULEMENT UNE FOIS LE DOMAINE ACHETE ET LES DNS POSES.
Sinon GitHub Pages sert le site sur un domaine qui ne resout pas.

    python scripts/migrer_domaine.py              # DRY-RUN, n'ecrit rien
    python scripts/migrer_domaine.py --yes        # ecrit pour de vrai
    python scripts/migrer_domaine.py --yes autre.com

Ce qu'il fait :
  1. remplace https://thejammerz.github.io par https://<domaine> partout
     (html, sitemap.xml, robots.txt, llms.txt, scripts/update_agenda.py)
  2. cree le fichier CNAME a la racine (c'est lui qui declenche GitHub Pages)
  3. rappelle les enregistrements DNS a poser chez le registrar

Apres le push il reste 3 choses A LA MAIN :
  - GitHub > Settings > Pages > Custom domain = <domaine>, puis cocher
    "Enforce HTTPS" une fois le certificat emis (peut prendre ~1 h)
  - Search Console : creer la propriete du nouveau domaine + resoumettre
    le sitemap. L'ancienne propriete github.io se garde, elle sert de preuve
    de redirection.
  - verifier que https://thejammerz.github.io/ redirige bien en 301
"""
import io, os, sys, glob

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANCIEN = u"thejammerz.github.io"

# IP officielles GitHub Pages pour un domaine racine (docs.github.com, lues le 31/08/2026)
IPV4 = ["185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153"]
IPV6 = ["2606:50c0:8000::153", "2606:50c0:8001::153",
        "2606:50c0:8002::153", "2606:50c0:8003::153"]

# Large exprès : tout fichier texte du depot doit passer sous le radar.
EXT = (".html", ".xml", ".txt", ".py", ".js", ".css", ".yml", ".yaml",
       ".json", ".md", ".webmanifest", ".svg")
IGNORE = (".git", "__pycache__")


def fichiers():
    """Piege : le depot s'appelle thejammerz.github.io, donc on ne teste JAMAIS
    les dossiers ignores en "sous-chaine" (".git" est dans ".github.io")."""
    moi = os.path.basename(os.path.abspath(__file__))
    for dossier, sous, noms in os.walk(RACINE):
        sous[:] = [d for d in sous if d not in IGNORE]
        for n in noms:
            if n.endswith(EXT) and n != moi:
                yield os.path.join(dossier, n)


def main():
    args = [a for a in sys.argv[1:]]
    ecrire = "--yes" in args
    args = [a for a in args if a != "--yes"]
    nouveau = args[0] if args else u"thejammerz.com"

    total, touches = 0, 0
    for p in fichiers():
        s = io.open(p, encoding="utf-8").read()
        n = s.count(ANCIEN)
        if not n:
            continue
        total += n
        touches += 1
        rel = os.path.relpath(p, RACINE).replace("\\", "/")
        print(u"  %-42s %3d remplacement(s)" % (rel, n))
        if ecrire:
            io.open(p, "w", encoding="utf-8", newline="").write(s.replace(ANCIEN, nouveau))

    cname = os.path.join(RACINE, "CNAME")
    if ecrire:
        io.open(cname, "w", encoding="utf-8", newline="").write(nouveau + u"\n")

    print(u"")
    print(u"%s : %d occurrence(s) dans %d fichier(s) -> %s"
          % (u"ECRIT" if ecrire else u"DRY-RUN", total, touches, nouveau))
    print(u"CNAME %s : %s" % (u"ecrit" if ecrire else u"a ecrire", cname))
    print(u"")
    print(u"DNS a poser chez le registrar pour %s :" % nouveau)
    for ip in IPV4:
        print(u"   A     @      %s" % ip)
    for ip in IPV6:
        print(u"   AAAA  @      %s" % ip)
    print(u"   CNAME www    thejammerz.github.io.")
    print(u"")
    if not ecrire:
        print(u"Rien n'a ete modifie. Relancer avec --yes pour appliquer.")


if __name__ == "__main__":
    main()
