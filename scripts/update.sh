#!/usr/bin/env bash

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${GREEN}=== Homelab v2 - Mise à jour ===${NC}"

# 1. Pull Git
echo -e "${YELLOW}[1/4] Récupération des dernières modifications du dépôt Git...${NC}"
if git pull; then
    echo -e "${GREEN}Code source mis à jour.${NC}"
else
    echo -e "${YELLOW}Attention : git pull a échoué (modifications locales détectées ?).${NC}"
fi

# 2. Pull Docker
echo -e "\n${YELLOW}[2/4] Téléchargement des nouvelles images de base...${NC}"
docker compose pull

# 3. Rebuild & Restart
echo -e "\n${YELLOW}[3/4] Reconstruction et relancement des services...${NC}"
docker compose up -d --build

# 4. Prune
echo -e "\n${YELLOW}[4/4] Nettoyage des anciennes images Docker obsolètes...${NC}"
docker image prune -f

echo -e "\n${GREEN}=== Stack mise à jour avec succès ! ===${NC}"
