# Jellyfin Invites

## Description
Service permettant de gérer et générer des codes d'invitation pour de nouveaux utilisateurs Jellyfin.

## Configuration
- Port interne : 3000.
- Volume : `./data/jellyfin-invites` (BDD SQLite, données).
- Variables d'environnement requises (dans le `.env` racine) :
  - `INVITE_ADMIN_USERNAME` / `INVITE_ADMIN_PASSWORD`
  - `JELLYFIN_API_KEY`
  - `INVITE_ENCRYPTION_KEY`
  - `SESSION_SECRET`

## Tests
Ce service possède une suite de tests automatisés (unitaires et intégration).
Pour les exécuter :
```bash
# Nécessite Docker
docker build -t jellyfin-invites-test -f services/jellyfin-invites/Dockerfile.test services/jellyfin-invites
docker run --rm --network homelab_homelab --env JELLYFIN_URL=http://jellyfin:8096 --env JELLYFIN_API_KEY=${JELLYFIN_API_KEY} jellyfin-invites-test
```
