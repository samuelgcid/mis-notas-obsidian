# Bot de trading autosuficiente

Implementación de las características descritas en
[[Wiki/Conceptos/Bot de trading autosuficiente]]. Es un bot **de seguimiento de
tendencia, solo largos y sin apalancamiento**, para mercados spot de cripto
(cualquier exchange soportado por [ccxt](https://github.com/ccxt/ccxt)).

> [!warning] Léelo antes de usarlo
> - **No hay garantía de beneficio.** Con datos sintéticos aleatorios el
>   backtest da un resultado ligeramente negativo, y eso es lo esperable: sin
>   tendencias reales, esta estrategia no tiene ventaja. Valídala con datos
>   reales (`backtest` + `walkforward`) antes de arriesgar nada.
> - Arranca **siempre en modo `paper`** (simulado con precios reales) durante
>   semanas. Después pasa a `live` con `sandbox: true` (testnet) y luego con
>   una cantidad pequeña.
> - Lo que hace autosuficiente al bot es que **sobrevive solo**, no que gane solo.

## Qué cubre de cada característica

| Característica | Cómo la implementa |
|---|---|
| 1. Estrategia con reglas explícitas | `bot/strategy.py`: EMA 20/50 + filtro de tendencia EMA 200, stop por ATR y trailing stop |
| 2. Validación | `backtest` (ejecución en la apertura siguiente, comisiones y deslizamiento) y `walkforward` (optimiza en un tramo y evalúa en el siguiente) |
| 3. Gestión de riesgo | `bot/risk.py`: 1 % de riesgo por operación, topes por posición y exposición, pausa por pérdida diaria, parada por drawdown, kill switch |
| 4. Ejecución fiable | `bot/broker.py`: reintentos con espera exponencial, `clientOrderId` para no duplicar órdenes, ajuste a la precisión y mínimos del mercado |
| 5. Resiliencia | Estado en SQLite (sobrevive a reinicios), reconciliación con la cuenta en cada vuelta, Docker con `restart: always`, modo seguro tras errores repetidos o datos raros |
| 6. Monitorización | Logs rotativos, alertas por Telegram, resumen diario, latido local (healthcheck de Docker) y externo (healthchecks.io) |
| 7. Adaptación controlada | Los parámetros solo cambian por decisión tuya tras un walk-forward; el bot nunca se reoptimiza en vivo |
| 8. Seguridad | Secretos solo por entorno, modo real bloqueado sin `BOT_CONFIRM_LIVE=yes`, contenedor sin root |
| 9. Sostenibilidad | Comisiones y deslizamiento incluidos en el tamaño y el PnL; historial de operaciones en `trades` para la contabilidad |
| 10. Ingeniería | Módulos separados (datos → señales → riesgo → ejecución → monitorización), misma estrategia en backtest y en real, tests |

## Cómo funciona cada vuelta (cada `loop_seconds`)

1. Escribe el latido y hace ping al servicio externo.
2. Lee precios y saldos, y **reconcilia**: si una posición ya no está en la
   cuenta (saltó el stop del exchange o vendiste a mano), la registra como cerrada.
3. Calcula el equity y comprueba los límites:
   - **Kill switch** o **drawdown ≥ 15 %** → cierra todo y se queda quieto.
   - **Pérdida diaria ≥ 3 %** → no abre nada nuevo hasta el día siguiente (UTC).
4. Para cada símbolo:
   - Si el precio toca el stop → vende.
   - Si las velas están congeladas o hay un movimiento anómalo → no decide nada y avisa.
   - Si hay posición: sale con señal bajista o sube el trailing stop.
   - Si no hay posición: entra cuando la tendencia alcista **acaba de confirmarse**,
     con el tamaño que arriesga un 1 % del capital hasta el stop.

## Instalación y uso — elige tu forma

Todas parten de la carpeta del proyecto (`cd Proyectos/bot-trading`) y siguen
el mismo camino: **instalar → configurar (`setup`) → comprobar (`check`) →
validar (`backtest`) → arrancar (`run`)**.

| Forma | Para qué | Cómo |
|---|---|---|
| A. Script de instalación | Probar en tu ordenador (Linux/macOS) | `./scripts/install.sh` y luego `./scripts/run.sh` |
| B. Windows | Probar en tu PC con Windows | `powershell -ExecutionPolicy Bypass -File scripts\install.ps1` y luego `.\scripts\run.ps1` |
| C. Makefile | Atajos para todo | `make install`, `make run`, `make help` |
| D. Docker | 24/7 en cualquier máquina con Docker | `make docker-check` y `make docker-up` |
| E. VPS con systemd | 24/7 en un servidor Linux sin Docker | `sudo ./scripts/deploy-vps.sh` |
| F. Manual | Control total | ver abajo |

### A/B/C. En tu ordenador

```bash
./scripts/install.sh          # crea .venv, instala, pasa los tests y lanza el asistente
./scripts/run.sh check        # comprobación previa
./scripts/run.sh              # arranca (Ctrl+C para parar de forma ordenada)
```

En Windows usa `scripts\install.ps1` y `scripts\run.ps1` con los mismos
comandos. Con `make`: `make install`, `make check`, `make run`.

> Para que opere 24/7 el ordenador tiene que estar siempre encendido y
> conectado. Para eso son mejores las opciones D o E.

### D. Docker (recomendado para 24/7)

```bash
python -m bot setup            # o: cp config.example.yaml config.yaml && cp .env.example .env
make docker-check              # comprobación previa dentro del contenedor
make docker-up                 # arranca en segundo plano con reinicio automático
make docker-logs               # ver qué hace
make docker-status             # posiciones y operaciones
make docker-down               # parar (las posiciones se conservan)
```

El contenedor corre con tu usuario (no como root), tiene un healthcheck
basado en el latido y guarda estado, logs y kill switch en `./data`.

### E. VPS Linux con systemd

En un VPS (Hetzner, DigitalOcean, Contabo, AWS Lightsail…) con Debian/Ubuntu:

```bash
git clone <tu-repo> && cd mis-notas-obsidian/Proyectos/bot-trading
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m bot setup              # crea config.yaml y .env
sudo ./scripts/deploy-vps.sh               # instala en /opt/bot-trading como servicio
```

El script crea un usuario `bot` sin privilegios, instala en
`/opt/bot-trading`, ejecuta la comprobación previa y activa el servicio
(`deploy/bot-trading.service`): arranca con el servidor, se reinicia si se
cae y solo puede escribir en `data/`. Volver a ejecutarlo actualiza el código
sin tocar tu configuración ni tu estado.

```bash
systemctl status bot-trading
journalctl -u bot-trading -f
cd /opt/bot-trading && sudo -u bot .venv/bin/python -m bot status
```

### F. Manual

```bash
pip install -r requirements-dev.txt
python -m bot setup
python -m bot check
python -m bot run
```

### Comandos

| Comando | Qué hace |
|---|---|
| `setup` | Asistente: modo, exchange, pares, perfil de riesgo (conservador/moderado/agresivo), claves y Telegram. Guarda `config.yaml` y `.env` (con permisos 600) |
| `check [--test-alert]` | Comprueba config, carpeta de datos, conexión, claves, que los pares existen, que tu capital llega al mínimo de orden y que las alertas están configuradas |
| `run` | Arranca el bucle de trading |
| `backtest --symbol X --since AAAA-MM-DD` | Backtest con datos históricos (o `--csv`) |
| `walkforward --symbol X --since AAAA-MM-DD` | Validación fuera de muestra |
| `status` | Modo, latido, límites, saldo, posiciones y últimas operaciones |
| `export [--output archivo.csv]` | Todas las operaciones a CSV, para la contabilidad e impuestos |
| `kill` / `resume` | Parada de emergencia (cierra todo) / reanudar |
| `reset-halt` | Reanudar tras una parada por drawdown |

### Pasar a dinero real

1. Crea claves de API **sin permiso de retirada** y restringidas a la IP del servidor.
2. `python -m bot setup` → modo `live`, **testnet: sí**.
3. `python -m bot check` hasta que todo salga ✅, y déjalo funcionar en testnet.
4. Cambia `sandbox: false` en `config.yaml`, añade `BOT_CONFIRM_LIVE=yes` a
   `.env`, y empieza con poco capital.

### Integración continua

`.github/workflows/bot-trading.yml` (en la raíz del repo) pasa los tests con
Python 3.10 y 3.12, comprueba la sintaxis de los scripts y construye la
imagen Docker en cada cambio de esta carpeta.

## Limitaciones conocidas

- Solo compra (largos) en spot; no opera en corto ni con apalancamiento.
- En modo `paper` el stop lo vigila el propio bot en cada vuelta, así que entre
  vueltas el precio puede pasarse del stop. En `live` intenta además dejar una
  orden stop en el exchange (si este no la soporta, avisa y la vigila el bot).
- El equity solo cuenta la moneda de cotización y las posiciones del bot; si
  usas la misma cuenta para otras cosas, los límites de riesgo se distorsionan.
  Usa una subcuenta dedicada.
- No se ha probado contra un exchange real desde este entorno (no tiene acceso
  de red a exchanges): la lógica está cubierta con tests y datos sintéticos, y
  la primera prueba real debe ser en `paper` y en testnet.
