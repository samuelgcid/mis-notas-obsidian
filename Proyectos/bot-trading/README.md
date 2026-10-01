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

## Uso

```bash
cd Proyectos/bot-trading
pip install -r requirements-dev.txt
cp config.example.yaml config.yaml     # ajusta símbolos, timeframe y riesgo
cp .env.example .env                   # claves y Telegram (opcional en paper)

python -m pytest -q                    # tests
python -m bot backtest --symbol BTC/USDT --since 2022-01-01
python -m bot walkforward --symbol BTC/USDT --since 2021-01-01 --folds 4
python -m bot run                      # arranca (paper por defecto)
python -m bot status                   # posiciones, saldo, últimas operaciones
python -m bot kill                     # cierra todo y deja de operar
python -m bot resume                   # quita el kill switch
python -m bot reset-halt               # reanuda tras una parada por drawdown
```

Para tenerlo 24/7 en un VPS:

```bash
mkdir -p data && sudo chown 1000:1000 data   # el contenedor no corre como root
docker compose up -d --build
docker compose logs -f
docker compose exec bot python -m bot status
```

### Pasar a dinero real

1. Crea claves de API **sin permiso de retirada** y restringidas a la IP del servidor.
2. En `config.yaml`: `mode: live` y, primero, `sandbox: true` (testnet).
3. En `.env`: `EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET` y `BOT_CONFIRM_LIVE=yes`.
4. Cuando la testnet vaya bien, `sandbox: false` con un capital pequeño.

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
