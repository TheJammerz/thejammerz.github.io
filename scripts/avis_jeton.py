#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A LANCER UNE SEULE FOIS, SUR TON ORDINATEUR. Ce petit programme obtient le
« jeton long » (refresh token) qui permettra ensuite au robot du site d'aller
lire tout seul, chaque nuit, les avis de la fiche Google Business Profile.

Rien n'est envoye nulle part : le jeton s'affiche dans ta fenetre, tu le
recopies dans les secrets du depot GitHub, et c'est fini pour toujours.

CE QU'IL FAUT AVANT (une seule fois, dans Google Cloud) :
  1. Un projet Google Cloud.
  2. L'API « Google My Business API » (et « My Business Account Management
     API ») activee dessus.
  3. L'acces demande via le formulaire « Application for Basic API Access »
     — sans ca, Google repond mais avec un quota de 0.
  4. Un ecran de consentement OAuth PUBLIE EN « PRODUCTION ». S'il reste en
     « Test », le jeton long meurt au bout de 7 jours et le robot s'arrete
     tout seul chaque semaine.
  5. Un identifiant OAuth de type « Application de bureau ». On en recopie
     l'identifiant et le secret ci-dessous.

UTILISATION :
    python scripts/avis_jeton.py
Si le serveur d'apercu du site tourne (port 8765), pas de souci : le
programme prend tout seul le port libre suivant.
Le navigateur s'ouvre, tu te connectes avec le compte PROPRIETAIRE de la
fiche, tu acceptes, et le jeton s'affiche ici.
"""
from __future__ import annotations

import http.server
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

PORTS = range(8765, 8776)   # 8765 sert deja au serveur d'apercu du site
ATTENTE = 300               # secondes : au-dela, Google ne reviendra plus
PORTAIL = "https://accounts.google.com/o/oauth2/v2/auth"
JETON = "https://oauth2.googleapis.com/token"
DROIT = "https://www.googleapis.com/auth/business.manage"

recu = {}


class Guichet(http.server.BaseHTTPRequestHandler):
    """Attrape le code que Google renvoie dans l'adresse de retour."""

    def do_GET(self):                                   # noqa: N802
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        recu.update({k: v[0] for k, v in params.items()})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        fini = "code" in recu
        self.wfile.write(
            ("<h2>%s</h2><p>Tu peux fermer cette page et revenir a la fenetre "
             "noire.</p>" % ("C'est bon." if fini else "Echec : Google n'a pas "
                             "renvoye de code.")).encode("utf-8"))

    def log_message(self, *a):                          # silence
        pass


def ouvrir_guichet():
    """Ouvre le petit guichet local sur le premier port libre.

    Le port 8765 est aussi celui du serveur d'apercu du site : si les deux
    tournent en meme temps, l'ancien code plantait avec une erreur systeme
    illisible. On essaie donc les suivants. Un identifiant OAuth de type
    << Application de bureau >> accepte n'importe quel port sur localhost.
    """
    dernier = None
    for port in PORTS:
        try:
            serveur = http.server.HTTPServer(("localhost", port), Guichet)
        except OSError as e:                         # port deja pris
            dernier = e
            continue
        serveur.timeout = ATTENTE
        return serveur, port
    print("Aucun port libre entre %d et %d (%s)." % (PORTS[0], PORTS[-1], dernier))
    print("Ferme le serveur d'apercu du site, puis relance.")
    sys.exit(1)


def demander(question: str) -> str:
    val = input(question).strip()
    if not val:
        print("Vide : j'arrete.")
        sys.exit(1)
    return val


def main() -> int:
    print(__doc__)
    cid = demander("Identifiant client OAuth (client_id) : ")
    secret = demander("Secret client (client_secret) : ")

    serveur, port = ouvrir_guichet()
    redirection = "http://localhost:%d" % port
    print("\nGuichet local ouvert sur le port %d." % port)

    adresse = PORTAIL + "?" + urllib.parse.urlencode({
        "client_id": cid,
        "redirect_uri": redirection,
        "response_type": "code",
        "scope": DROIT,
        # indispensables : sans eux Google ne redonne pas de jeton long
        "access_type": "offline",
        "prompt": "consent",
    })
    print("\nJ'ouvre le navigateur. Connecte-toi avec le compte PROPRIETAIRE "
          "de la fiche Google.\nSi rien ne s'ouvre, colle cette adresse a la "
          "main :\n\n%s\n" % adresse)
    try:
        webbrowser.open(adresse)
    except Exception:                                    # noqa: BLE001
        pass

    serveur.handle_request()
    serveur.server_close()

    if not recu:
        # Sans minuterie, ce cas laissait la fenetre figee pour toujours :
        # on attendait un retour de Google qui n'arrivera jamais.
        print("\nRien recu en %d secondes : Google n'est jamais revenu ici."
              % ATTENTE)
        print("Cause la plus frequente : l'identifiant OAuth n'est pas de type "
              "<< Application de bureau >>. Recree-le dans Google Cloud avec "
              "ce type-la.")
        print("Autre cause : l'adresse n'a jamais ete ouverte. Recolle-la a "
              "la main dans le navigateur.")
        return 1

    if "code" not in recu:
        print("\nEchec : pas de code. Detail : %s" % recu.get("error", "inconnu"))
        return 1

    corps = urllib.parse.urlencode({
        "code": recu["code"],
        "client_id": cid,
        "client_secret": secret,
        "redirect_uri": redirection,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    req = urllib.request.Request(JETON, data=corps, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as rep:
            reponse = json.loads(rep.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Sans ca, Google explique le probleme en un mot... dans un corps de
        # reponse que personne ne lit, et l'ecran n'affiche qu'un « HTTP Error
        # 400 » incomprehensible. C'est un outil a lancer UNE fois : l'erreur
        # muette coute la manipulation entiere.
        detail = e.read().decode("utf-8", "replace")[:600]
        print("\nGoogle refuse l'echange (%s) : %s" % (e.code, detail))
        if e.code in (400, 401):
            print("Le plus souvent : le SECRET client a ete mal recopie "
                  "(« invalid_client »). Reprends-le dans la console Google "
                  "Cloud, ou recree l'identifiant OAuth — type « Application "
                  "de bureau », pas « Application Web ».")
        return 1

    long_jeton = reponse.get("refresh_token")
    if not long_jeton:
        print("\nGoogle n'a pas renvoye de jeton long. C'est presque toujours "
              "parce que le compte a deja accepte : va sur "
              "https://myaccount.google.com/permissions, retire l'acces de "
              "cette application, et relance.")
        return 1

    print("\n" + "=" * 70)
    print("A COLLER DANS LES SECRETS DU DEPOT GITHUB")
    print("  GBP_CLIENT_ID      = %s" % cid)
    print("  GBP_CLIENT_SECRET  = %s" % secret)
    print("  GBP_REFRESH_TOKEN  = %s" % long_jeton)
    print("=" * 70)
    print("\nNe colle ce jeton nulle part ailleurs : il donne le droit de "
          "gerer la fiche Google.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
