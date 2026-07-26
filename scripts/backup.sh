#!/usr/bin/env bash

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

BACKUP_DIR="backups"
MAX_BACKUPS=5
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/homelab_backup_${TIMESTAMP}.tar.gz"

echo -e "${GREEN}=== Homelab v2 - Sauvegarde ===${NC}"

mkdir -p "$BACKUP_DIR"

echo -e "${YELLOW}Création de la sauvegarde dans ${BACKUP_FILE}...${NC}"

# On exclut le cache de Jellyfin et les répertoires temporaires pour économiser de la place
tar --exclude='data/jellyfin/cache' \
    --exclude='data/jellyfin/transcoding-temp' \
    -czf "$BACKUP_FILE" data .env

echo -e "${GREEN}Sauvegarde terminée avec succès ! Taille : $(du -sh "$BACKUP_FILE" | cut -f1)${NC}"

# Nettoyage des anciennes sauvegardes
echo -e "${YELLOW}Vérification des anciennes sauvegardes (max conservées : $MAX_BACKUPS)...${NC}"
BACKUP_COUNT=$(ls -1 ${BACKUP_DIR}/homelab_backup_*.tar.gz 2>/dev/null | wc -l)

if [ "$BACKUP_COUNT" -gt "$MAX_BACKUPS" ]; then
    EXCESS=$((BACKUP_COUNT - MAX_BACKUPS))
    echo -e "Suppression de $EXCESS ancienne(s) sauvegarde(s)..."
    ls -1tr ${BACKUP_DIR}/homelab_backup_*.tar.gz | head -n "$EXCESS" | xargs rm -f
    echo -e "${GREEN}Nettoyage terminé.${NC}"
else
    echo -e "${GREEN}Aucune ancienne sauvegarde à supprimer (Total: $BACKUP_COUNT).${NC}"
fi
