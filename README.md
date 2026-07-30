# Portfolio Dashboard

Panel web auto-actualizable para visualizar tenencias de acciones agrupadas por broker, con gráfico de torta y precios en vivo desde Yahoo Finance.

## Stack

- **Backend:** Python + Flask
- **Frontend:** Bootstrap 5 (dark mode) + Chart.js
- **Precios:** Yahoo Finance (vía `yfinance`)
- **Datos:** SQLite (`portfolio.db`)
- **Infra:** Docker Compose

## Funcionalidades

-   **Auto-actualización** — Al entrar al panel o presionar "Actualizar precios", obtiene cotizaciones vía Yahoo Finance para todos los tickers.
-   **Gráfico de torta** — Distribución porcentual del portfolio agregando el mismo ticker a través de todos los brokers.
-   **Tabla de tenencias** — Ticker, empresa, broker, cantidad de shares, precio, valor total y porcentaje.
-   **Cards por broker** — Desglose individual de cada broker con sus propias tablas y subtotales.
-   **Resumen** — Total cartera, cantidad de brokers, tickers y precios actualizados.
-   **Multi-activo** — Soporta acciones US, acciones argentinas (BYMA, con sufijo `.BA`), CEDEARs, y crypto (BTC/ETH).

## Requisitos

- Docker y Docker Compose

## Quick Start

```bash
git clone <repo-url> portfolio-dashboard
cd portfolio-dashboard

# Copiar tu base de datos (o usar la de ejemplo)
cp ruta/a/tu/portfolio.db data/portfolio.db

# Iniciar
docker compose up -d
```

Abrir [http://localhost:5050](http://localhost:5050)

## Estructura

```
portfolio-dashboard/
├── app.py                  # Backend Flask
├── index.html              # Frontend (Bootstrap + Chart.js)
├── Dockerfile              # Imagen Docker
├── docker-compose.yml      # Orquestación
├── requirements.txt        # Dependencias Python
├── data/
│   ├── portfolio.db        # Base SQLite (con precios)
│   └── portfolio_dump.sql  # Dump SQL de la base
└── README.md
```

## Configuración

| Variable     | Default                | Descripción                     |
|-------------|------------------------|--------------------------------|
| `PORTFOLIO_DB` | `/data/portfolio.db` | Ruta a la base SQLite          |
| `HOST`        | `0.0.0.0`            | Interfaz de red del servidor    |
| `PORT`        | `5050`               | Puerto del servidor             |

## Base de datos

### holdings

| Columna       | Tipo     | Descripción                              |
|--------------|----------|------------------------------------------|
| ticker       | TEXT PK  | Símbolo de la acción                     |
| company      | TEXT     | Nombre de la empresa                     |
| shares       | REAL     | Cantidad de acciones                     |
| sector       | TEXT     | Sector                                   |
| broker       | TEXT PK  | Nombre del broker                        |
| cedear_ratio | REAL     | Ratio de conversión CEDEAR               |
| is_cedear    | INTEGER  | 1 si es CEDEAR                           |
| is_crypto    | INTEGER  | 1 si es crypto                           |
| updated_at   | TEXT     | Última actualización                     |

### prices

| Columna     | Tipo     | Descripción                     |
|------------|----------|---------------------------------|
| id         | INTEGER  | PK autoincremental              |
| ticker     | TEXT     | Símbolo (referencia a holdings) |
| price      | REAL     | Precio de cierre                |
| currency   | TEXT     | USD o ARS                       |
| recorded_at| TEXT     | Timestamp de la cotización      |

### Restaurar desde dump

```bash
sqlite3 data/portfolio.db < data/portfolio_dump.sql
```

## Mapa de tickers a Yahoo Finance

| Origen          | Ticker local | Yahoo Finance   | Moneda |
|----------------|-------------|-----------------|--------|
| BECA Vestiva   | AMD, MSFT…  | directo (AMD)   | USD    |
| TM Inversiones | ALUA, PAMP… | +.BA (ALUA.BA)  | ARS    |
| Balanz         | ALAB, ARM…  | directo (ALAB)  | USD    |
| Belo           | BTC, ETH    | -USD (BTC-USD)  | USD    |

## Desarrollo local (sin Docker)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp ~/.hermes/portfolio.db data/
python3 app.py
```
