# Homelab v2

Ce dépôt contient la configuration et l'orchestration de mon Homelab via Docker Compose.

## 🚀 Installation rapide

1. Assurez-vous que Docker et Docker Compose sont installés.
2. Clonez le dépôt et rendez-vous à la racine.
3. Exécutez le script d'installation :
   ```bash
   chmod +x scripts/*.sh
   ./scripts/install.sh
   ```
   *Le script configurera automatiquement les paramètres système. Cependant, certaines variables sensibles nécessitent votre attention (voir section Configuration).*

## ⚙️ Configuration

Avant ou après la première exécution, éditez le fichier `.env` généré à la racine pour configurer les services :

- **`INVITE_ADMIN_USERNAME` / `INVITE_ADMIN_PASSWORD`** : Identifiants administrateur pour Jellyfin-Invites (à changer impérativement).
- **`JELLYFIN_API_KEY`** : Clé API requise pour la liaison entre Jellyfin et Jellyfin-Invites.
- **`PRINTER_IP`** : IP de votre imprimante 3D (si utilisé).

*(Note : Si `INVITE_ENCRYPTION_KEY` et `SESSION_SECRET` sont laissés vides, le script les générera automatiquement.)*

## 🛠 Administration

Le dossier `scripts/` contient tous les outils nécessaires à la maintenance :

| Script | Rôle |
| :--- | :--- |
| `./scripts/install.sh` | Initialisation complète (dépendances, .env, conteneurs) |
| `./scripts/backup.sh` | Sauvegarde compressée des données et du .env |
| `./scripts/restore.sh` | Restauration interactive des données |
| `./scripts/update.sh` | Mise à jour du code et des images Docker |
| `./scripts/healthcheck.sh` | Diagnostic de santé complet des services |
| `./scripts/logs.sh` | Visualisation des logs (usage : `./scripts/logs.sh <service>`) |

## 📦 Services

- **Nginx Proxy Manager** : Gestionnaire de reverse proxy et certificats SSL.
- **Jellyfin** : Serveur média.
- **Jellyfin-Invites** : Service de gestion d'invitations Jellyfin.
- **Filebrowser** : Explorateur de fichiers distant.
- **Hub3D** : Backend et frontend pour l'impression 3D.
