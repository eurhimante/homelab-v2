#!/usr/bin/env bash

set -e

# Couleurs pour l'affichage
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== Homelab v2 - Installation ===${NC}"

# Racine du projet
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 1. Vérification des dépendances
echo -e "\n${YELLOW}[1/5] Vérification des dépendances...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Erreur : Docker n'est pas installé. Veuillez l'installer avant de continuer.${NC}"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo -e "${RED}Erreur : Docker Compose (v2) n'est pas disponible.${NC}"
    exit 1
fi
echo -e "${GREEN}Docker et Docker Compose sont opérationnels !${NC}"

# 2. Création des dossiers
echo -e "\n${YELLOW}[2/5] Création des dossiers de données persistantes...${NC}"
mkdir -p data/npm/data data/npm/letsencrypt \
         data/jellyfin-invites \
         data/jellyfin/config data/jellyfin/cache \
         data/filebrowser/database data/filebrowser/config \
         backups

# Gestion de l'arborescence pour /mnt/rasplex
if [ ! -d "/mnt/rasplex" ]; then
    echo -e "${YELLOW}Avertissement : /mnt/rasplex n'existe pas localement.${NC}"
    echo -e "Création d'un dossier temporaire local dans ./data/media pour éviter les plantages du conteneur."
    mkdir -p data/media
    echo -e "Note : Pensez à monter votre stockage externe sur /mnt/rasplex ou à éditer compose.yaml.${NC}"
fi

# 3. Création et configuration de l'environnement (.env)
echo -e "\n${YELLOW}[3/5] Configuration du fichier d'environnement (.env)...${NC}"
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${GREEN}Fichier .env créé avec succès à partir de .env.example.${NC}"
    else
        echo -e "${RED}Erreur : .env.example introuvable à la racine.${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}Le fichier .env existe déjà.${NC}"
fi

# Remplacement des variables par défaut par celles du système local
USER_PUID=$(id -u)
USER_PGID=$(id -g)
SYSTEM_TZ=$(cat /etc/timezone 2>/dev/null || echo "Europe/Paris")

set_env_val() {
    local key=$1
    local val=$2
    if grep -q "^${key}=" .env; then
        if grep -q "^${key}=\s*$" .env || grep -q "^${key}=change_me" .env; then
            sed -i "s|^${key}=.*|${key}=${val}|" .env
        fi
    else
        echo "${key}=${val}" >> .env
    fi
}

set_env_val "PUID" "$USER_PUID"
set_env_val "PGID" "$USER_PGID"
set_env_val "TZ" "$SYSTEM_TZ"

# Génération automatique de clés uniques sécurisées si vides
if grep -q "^INVITE_ENCRYPTION_KEY=\s*$" .env || grep -q "^INVITE_ENCRYPTION_KEY=$" .env; then
    RAND_HEX_KEY=$(openssl rand -hex 16 2>/dev/null || echo "env_key_$(date +%s)_$RANDOM")
    sed -i "s|^INVITE_ENCRYPTION_KEY=.*|INVITE_ENCRYPTION_KEY=${RAND_HEX_KEY}|" .env
fi

if grep -q "^SESSION_SECRET=\s*$" .env || grep -q "^SESSION_SECRET=$" .env; then
    RAND_HEX_SEC=$(openssl rand -hex 32 2>/dev/null || echo "sec_key_$(date +%s)_$RANDOM")
    sed -i "s|^SESSION_SECRET=.*|SESSION_SECRET=${RAND_HEX_SEC}|" .env
fi

echo -e "${GREEN}Configuration .env mise à jour (PUID=$USER_PUID, PGID=$USER_PGID, TZ=$SYSTEM_TZ).${NC}"

# 4. Lancement de la stack
echo -e "\n${YELLOW}[4/5] Lancement des conteneurs via Docker Compose...${NC}"
docker compose pull || echo -e "${YELLOW}Téléchargement partiel, reconstruction locale...${NC}"
docker compose up -d --build

# 5. Diagnostic initial
echo -e "\n${YELLOW}[5/5] Vérification initiale de l'état des services...${NC}"
sleep 3
docker compose ps

echo -e "\n${GREEN}=== Installation Terminée avec Succès ! ===${NC}"
echo -e "Services accessibles localement :"
echo -e "- Nginx Proxy Manager (Admin) : http://localhost:81"
echo -e "- File Browser : http://localhost:8081"
echo -e "- Jellyfin : http://localhost:8096"
echo -e "- Hub3D Backend (API) : http://localhost:8000"
echo -e "\nCommandes d'administration utiles :"
echo -e "- Voir les logs : ./scripts/logs.sh"
echo -e "- Tester la santé des services : ./scripts/healthcheck.sh"
