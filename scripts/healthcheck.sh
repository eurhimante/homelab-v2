#!/usr/bin/env bash

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${GREEN}=== Homelab v2 - Diagnostic de Santé ===${NC}"

check_http() {
    local name=$1
    local url=$2
    local expected_code=$3
    
    echo -ne "Vérification [${name}] (${url}) : "
    local http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$url" || true)
    
    if [ "$http_code" = "$expected_code" ] || { [ "$expected_code" = "200" ] && [[ "$http_code" =~ ^(200|301|302|307)$ ]]; }; then
        echo -e "${GREEN}OK (HTTP $http_code)${NC}"
        return 0
    else
        echo -e "${RED}ÉCHEC (HTTP $http_code, attendu: $expected_code)${NC}"
        return 1
    fi
}

# 1. Liste des conteneurs
echo -e "\n${YELLOW}[1/2] État des Conteneurs Docker :${NC}"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.State}}"

# 2. Tests de connectivité réseau réelle
echo -e "\n${YELLOW}[2/2] Tests d'accessibilité HTTP (ports locaux) :${NC}"
FAILED=0

check_http "Jellyfin" "http://localhost:8096/health" "200" || FAILED=$((FAILED + 1))
check_http "File Browser" "http://localhost:8081" "200" || FAILED=$((FAILED + 1))
check_http "Nginx Proxy Manager Admin" "http://localhost:81" "200" || FAILED=$((FAILED + 1))
check_http "Hub3D Backend (API)" "http://localhost:8000/health" "200" || FAILED=$((FAILED + 1))

if [ "$FAILED" -eq 0 ]; then
    echo -e "\n${GREEN}Génial ! Tous les services fonctionnent et répondent parfaitement.${NC}"
    exit 0
else
    echo -e "\n${RED}Attention : $FAILED service(s) dysfonctionnel(s) détecté(s).${NC}"
    exit 1
fi
