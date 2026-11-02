# Contribuer à Asteria Hub

Décrivez le problème, le système d’exploitation, la version de Python ou de l’exécutable et les étapes permettant de le reproduire. Masquez les chemins personnels et n’envoyez aucun jeu, clé ou firmware.

Avant une pull request, installez `requirements-dev.txt`, puis lancez `python -m pytest -q` et `python tests/browser_smoke.py` après installation de Chromium avec Playwright. Pour un changement d’interface, joignez une capture avec des données fictives et vérifiez l’affichage mobile.

Le lancement doit rester local, sans téléchargement automatique, sans modification des jeux et sans dépendance à un chemin propre à une machine. Les fichiers personnels restent hors du dépôt. L’API utilise des identifiants de bibliothèque plutôt que des chemins fournis par le navigateur pour lancer un jeu.

Les suggestions de compatibilité doivent être sourcées et datées. Ne présentez pas une commande de lancement réussie comme une preuve que le jeu fonctionne correctement dans un émulateur.
