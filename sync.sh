#!/usr/bin/env bash
# ==============================================================================
# Script de sincronización automática para JARVIS
# Repositorio: https://github.com/JuanCL21/J.A.R.V.I.S
# ==============================================================================
set -e

# Asegurar que estamos en el directorio del proyecto
cd "$(dirname "$0")"

echo "=================================================="
echo "🤖 Sincronizando JARVIS con GitHub..."
echo "=================================================="

# 1. Validar integridad ejecutando los tests
echo "🧪 [1/4] Verificando pruebas unitarias..."
if [ -f "venv/bin/pytest" ]; then
    venv/bin/pytest ui/ tests/ -q
else
    pytest ui/ tests/ -q
fi
echo "   ✅ Todas las pruebas pasaron satisfactoriamente."

# 2. Agregar cambios (respetando .gitignore)
echo "📦 [2/4] Preparando archivos modificados..."
git add .

# 3. Comprobar si hay cambios para confirmar
if git diff-index --quiet HEAD --; then
    echo "✨ No hay cambios locales pendientes por confirmar."
else
    # Si se pasó un mensaje como argumento, usarlo; sino generar uno con fecha/hora
    MSG="${1:-"actualización automática: $(date '+%Y-%m-%d %H:%M:%S')"}"
    echo "💾 [3/4] Creando commit: '$MSG'..."
    git commit -m "$MSG"
fi

# 4. Sincronizar y subir a GitHub
echo "🚀 [4/4] Subiendo a GitHub (rama main)..."
# Pull con rebase por si hubo cambios remotos
git pull --rebase origin main 2>/dev/null || true
git push origin main

echo "=================================================="
echo "🎉 ¡Repositorio actualizado y sincronizado con éxito!"
echo "   Ver en: https://github.com/JuanCL21/J.A.R.V.I.S"
echo "=================================================="
