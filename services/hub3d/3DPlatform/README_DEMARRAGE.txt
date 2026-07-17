VERSION STABLE - Ender 3 V3 KE + Moonraker

1) Backend
   Ouvrir PowerShell dans 3DPlatform\print_engine
   python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

   Si uvicorn n'est pas installé :
   pip install -r requirements.txt

2) Frontend
   Ouvrir PowerShell dans 3DPlatform\print_engine_front
   npm install
   npm.cmd run dev -- --host 0.0.0.0

3) URL depuis le serveur
   http://localhost:5173/

4) URL depuis un autre PC du réseau
   http://192.168.1.162:5173/

5) Config réseau frontend
   Fichier : print_engine_front\.env
   VITE_API_URL=http://192.168.1.162:8000

6) Imprimante
   Interface Creality : http://192.168.1.193/#/home
   Moonraker API : http://192.168.1.193:7125

7) Ajouts inclus
   - Choix imprimante
   - Choix filament
   - Templates 3MF : PLA / TPU60 / TPU90 / ABS / PETG si les fichiers existent
   - Scale STL dans le 3MF
   - Quantité : duplication dans le 3MF
   - Envoi G-code vers Moonraker
   - Lancement impression

IMPORTANT
Ne pas copier par-dessus un ancien dossier avec node_modules ouvert.
Extraire dans un nouveau dossier propre, puis lancer npm install.
