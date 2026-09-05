# J.A.R.V.I.S
> **Just A Rather Very Intelligent System** — Asistente de Escritorio Local con Interfaz Neural Obsidian Assistant (PyQt6), Orbe Reactivo Procedural y Enclave Seguro de Ejecución.

[![Tests](https://img.shields.io/badge/Tests-121%20Passed-14b8a6.svg?style=flat-square)]()
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-0ea5e9.svg?style=flat-square)]()
[![UI](https://img.shields.io/badge/UI-PyQt6%20Pure-89ceff.svg?style=flat-square)]()
[![Privacy](https://img.shields.io/badge/Security-Local%20Enclave%20%2F%20Zero%20Exfiltration-22c55e.svg?style=flat-square)]()

---

## 🌟 Características Principales

1. **Orbe Neural Reactivo Multi-Capa (AI Orb v2)**:
   - Motor matemático procedural basado en el modelo de color contextual **HSL** (`hue: 216`).
   - Modulación dinámica por estado (`idle`, `listening`, `speaking`) con respiración elástica y deriva especular guiada por el puntero del ratón.
   - 3 anillos orbitales punteados en rotación diferencial continua.
   - Proyección 3D de constelación de Fibonacci sobre lienzo 2D ultra-optimizado (>200 FPS).

2. **Entorno de Chat Operativo con Análisis Vectorial**:
   - Componente nativo vectorial de gráficos (`TrendChartWidget` con QPainter).
   - Resumen interactivo de registros y artefactos generados (`.parquet`, `.png`).
   - Sidecar de telemetría de sandbox (monitor de RAM en tiempo real y reglas de confinamiento POSIX).

3. **Catálogo Unificado de Plugins con Aislamiento Sandbox**:
   - Descubrimiento, instalación y gestión de extensiones locales.
   - Confinamiento estricto sin exfiltración de datos hacia redes externas no autorizadas.

4. **Configuración de Enclave y Almacenamiento Seguro**:
   - Gestión de claves de API (Gemini Live Core) con permisos restrictivos `0600` en almacenamiento local cifrado (`ENCRYPTED_STORE`).
   - Verificador de conexión en segundo plano y parámetros de aislamiento global.

---

## 🚀 Instalación y Puesta en Marcha

### Prerrequisitos
- Python 3.11 o superior.
- Git.
- Entorno de escritorio Linux (X11 o Wayland).

### 1. Clonar el repositorio
```bash
git clone git@github.com:JuanCL21/J.A.R.V.I.S.git
cd J.A.R.V.I.S
```

### 2. Crear entorno virtual e instalar dependencias
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Ejecutar la aplicación
```bash
python ui/app.py
```

### 4. Ejecutar la suite de pruebas (121 tests)
```bash
pytest ui/ tests/
```

---

## 🔄 Sincronización y Actualización Automática

El proyecto incluye un script helper `sync.sh` para verificar la salud del código y subir los cambios a GitHub en un solo paso:

```bash
# Sincronización automática con mensaje de fecha y hora
./sync.sh

# O especificando un mensaje descriptivo para el commit
./sync.sh "feat: mejoras en el renderizado del orbe neural"
```

---

## 🛡️ Seguridad y Privacidad
JARVIS está diseñado bajo el principio de **Zero Exfiltration**:
- Los datos y transacciones se procesan localmente en el sandbox del sistema.
- Las variables secretas (`.env`, llaves de API) están estrictamente ignoradas por Git y aisladas en el enclave seguro.

---

## 👤 Autor
Desarrollado por [JuanCL21](https://github.com/JuanCL21).
