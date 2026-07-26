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

echo -e "${GREEN}=== Homelab v2 - Restauration ===${NC}"

SELECTED_BACKUP=""
if [ -n "$1" ]; then
    if [ -f "$1" ]; then
        SELECTED_BACKUP="$1"
    else
        echo -e "${RED}Erreur : Le fichier spécifié n'existe pas : $1${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}Recherche des sauvegardes disponibles...${NC}"
    BACKUPS=($(ls -1tr ${BACKUP_DIR}/homelab_backup_*.tar.gz 2>/dev/null || true))
    
    if [ ${#BACKUPS[@]} -eq 0 ]; then
        echo -e "${RED}Aucune sauvegarde trouvée dans le dossier '${BACKUP_DIR}'.${NC}"
        exit 1
    fi
    
    echo -e "Sélectionnez l'archive à restaurer :"
    for i in "${!BACKUPS[@]}"; do
        echo -e "[$i] $(basename "${BACKUPS[$i]}") - $(du -sh "${BACKUPS[$i]}" | cut -f1)"
    done
    
    read -p "Entrez le numéro correspondant (0-$(( ${#BACKUPS[@]} - 1 ))) : " CHOICE
    
    if [[ ! "$CHOICE" =~ ^[0-9]+$ ]] || [ "$CHOICE" -lt 0 ] || [ "$CHOICE" -ge "${#BACKUPS[@]}" ]; then
        echo -e "${RED}Sélection incorrecte. Restauration annulée.${NC}"
        exit 1
    fi
    
    SELECTED_BACKUP="${BACKUPS[$CHOICE]}"
fi

echo -e "\n${YELLOW}Sauvegarde choisie : $(basename "$SELECTED_BACKUP")${NC}"
read -p "ATTENTION : Cette action va supprimer définitivement l'état actuel de ./data. Continuer ? (y/N) : " CONFIRM
if [[ ! "$CONFIRM" =~ ^[yY](es)?$ ]]; then
    echo -e "${RED}Restauration annulée.${NC}"
    exit 0
fi

# 1. Couper les conteneurs
echo -e "\n${YELLOW}[1/3] Arrêt de la stack Docker Compose...${NC}"
docker compose down

# 2. Restaurer les données
echo -e "\n${YELLOW}[2/3] Extraction des fichiers...${NC}"
rm -rf data
tar -xzf "$SELECTED_BACKUP"
echo -e "${GREEN}Données restaurées !${NC}"

# 3. Relancer la stack
echo -e "\n${YELLOW}[3/3] Redémarrage de la stack Docker Compose...${NC}"
docker compose up -d

echo -e "\n${GREEN}=== Restauration de la stack terminée avec succès ! ===${NC}"
