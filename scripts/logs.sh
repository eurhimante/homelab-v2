#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ $# -gt 0 ]; then
    # Passe les arguments utilisateur directement (ex: -f jellyfin)
    docker compose logs "$@"
else
    # Comportement par défaut : affiche les 100 dernières lignes et suit l'activité
    docker compose logs -f --tail=100
fi
