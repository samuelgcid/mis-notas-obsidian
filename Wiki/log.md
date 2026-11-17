# Log

Registro cronológico y append-only de lo que ha pasado en esta wiki:
ingestas, consultas archivadas y pases de lint. Formato de cada entrada, ver
[[../CLAUDE.md]]:

```
## [YYYY-MM-DD] tipo | Título
```

`tipo` es uno de: `ingesta`, `consulta`, `lint`.

---

## [2026-09-17] lint | Bootstrap de la wiki

Se creó la estructura inicial del repositorio siguiendo el patrón LLM Wiki:
`Fuentes/`, `Wiki/` (con `index.md`, `log.md`, `Entidades/`, `Conceptos/`,
`Resumenes/`) y el esquema en `CLAUDE.md`. Aún no hay fuentes ingeridas.

## [2026-10-01] consulta | Características de un bot de trading autosuficiente

Respuesta archivada como [[Wiki/Conceptos/Bot de trading autosuficiente]]
(conocimiento general; aún sin fuentes sobre trading). A partir de ella se
creó el proyecto de código `Proyectos/bot-trading/`: estrategia de
seguimiento de tendencia (EMA 20/50/200 + ATR), gestión de riesgo (1 % por
operación, pérdida diaria, drawdown, kill switch), estado persistente en
SQLite, reconciliación, alertas por Telegram, heartbeat, backtest,
walk-forward, Docker y tests. Se añadió la carpeta `Proyectos/` al esquema.

## [2026-11-17] consulta | Montar un canal de clipping

El usuario quiere un canal de clipping (YouTube Shorts, TikTok, Instagram
Reels) con vídeos largos de otros creadores: el agente elige los mejores
momentos y los pasa a 9:16. Se creó [[Wiki/Conceptos/Canal de clipping]] y
el proyecto `Proyectos/canal-clipping/` (descarga, transcripción, corte
vertical, subida a las tres plataformas, crédito obligatorio, privado por
defecto, tests del corte).
