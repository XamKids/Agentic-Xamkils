"""XamKids Profile : point d'entrée de la plateforme web (Flask).

Lancement : ./lancer.sh   puis ouvrir l'adresse affichée dans le terminal
"""
import os

from xamkids.web import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8501")), threaded=True)
