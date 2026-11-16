"""XamKids Profile : point d'entrée de la plateforme web (Flask).

Lancement : ./lancer.sh   puis ouvrir l'adresse affichée dans le terminal
"""
from xamkids.web import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8501, threaded=True)
