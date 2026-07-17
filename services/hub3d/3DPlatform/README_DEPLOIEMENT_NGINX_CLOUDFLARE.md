# Déploiement Hub 3D avec Nginx + Cloudflare

## Configuration incluse

Imprimante configurée :

```txt
Ender 3 V3 KE
IP imprimante : 192.168.1.193
Moonraker API : http://192.168.1.193:7125
Interface Creality : http://192.168.1.193/#/home
```

Le navigateur ne contacte pas Moonraker directement. Le chemin est :

```txt
Utilisateur → Cloudflare → Nginx → FastAPI → Moonraker → Ender 3 V3 KE
```

## Nouveautés ajoutées

- Dashboard live imprimante.
- État : prête, impression en cours, pause, erreur, hors ligne.
- Fichier en cours.
- Progression en %.
- Temps écoulé.
- Temps restant estimé.
- Température buse.
- Température plateau.
- Message erreur / message Klipper.
- Refresh automatique toutes les 3 secondes.
- Frontend prêt pour reverse proxy : `VITE_API_URL=/api`.

---

# 1. Préparer le backend FastAPI

Sur le serveur :

```powershell
cd C:\3DPlatform\print_engine
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Pourquoi `127.0.0.1` ?

Parce que Nginx sera le seul point d’entrée public. FastAPI reste local au serveur.

Test local serveur :

```powershell
curl http://127.0.0.1:8000/printer/config
curl http://127.0.0.1:8000/printer/live-status
```

---

# 2. Préparer le frontend React

Dans :

```txt
C:\3DPlatform\print_engine_front\.env
```

mettre :

```env
VITE_API_URL=/api
```

Puis build :

```powershell
cd C:\3DPlatform\print_engine_front
npm install
npm run build
```

Cela crée :

```txt
C:\3DPlatform\print_engine_front\dist
```

---

# 3. Configurer Nginx

Un fichier prêt est inclus :

```txt
C:\3DPlatform\nginx_hub3d.conf
```

Copie son contenu dans ta configuration Nginx, ou inclus-le depuis `nginx.conf`.

Configuration importante :

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000/;
}
```

Le slash final est important. Il transforme :

```txt
/api/printer/config
```

en :

```txt
http://127.0.0.1:8000/printer/config
```

Après modification Nginx :

```powershell
nginx -t
nginx -s reload
```

Si Nginx n’est pas dans le PATH, lance ces commandes depuis le dossier d’installation Nginx.

---

# 4. Configurer Cloudflare

## Option A — Cloudflare DNS classique

Dans Cloudflare DNS :

```txt
Type : A
Name : hub3d
IPv4 : IP publique de ton serveur
Proxy : activé, nuage orange
```

L’URL sera :

```txt
https://hub3d.ton-domaine.com
```

Dans SSL/TLS, utilise idéalement :

```txt
Full ou Full strict
```

## Option B — Cloudflare Tunnel

Dans Zero Trust / Tunnel, ajoute un public hostname :

```txt
Subdomain : hub3d
Domain : ton-domaine.com
Service : http://localhost:80
```

Cloudflare pointera vers Nginx, puis Nginx vers FastAPI.

---

# 5. Tests

Depuis le serveur :

```powershell
curl http://127.0.0.1:8000/printer/config
curl http://127.0.0.1:8000/printer/live-status
```

Depuis un navigateur :

```txt
http://localhost
```

Puis via Cloudflare :

```txt
https://hub3d.ton-domaine.com
```

---

# 6. Important sécurité

Ne jamais exposer directement Moonraker sur Internet :

```txt
À ne pas faire : https://domaine.com → 192.168.1.193:7125
```

Moonraker doit rester accessible uniquement depuis le réseau local :

```txt
FastAPI → http://192.168.1.193:7125
```

---

# 7. Remarque Cloudflare

Les uploads ou opérations de slicing très longs peuvent être sensibles aux limites de requêtes côté proxy. Pour un usage intensif, l’évolution propre sera de transformer slicing/upload en tâches asynchrones avec suivi d’avancement. Cette version reste prête à lancer pour ton usage actuel.
