---
tags: [trading, automatizacion, gestion-de-riesgo]
creado: 2026-10-01
actualizado: 2026-10-01
---
# Bot de trading autosuficiente

Un bot de trading **autosuficiente** opera, se protege y se recupera de fallos
sin supervisión constante. Ningún bot lo es al 100 %: los mercados cambian y
una ventaja que funciona hoy puede dejar de funcionar. Siempre hace falta una
persona que lo revise de vez en cuando.

> [!note] Origen
> Respuesta a una consulta del 2026-10-01, basada en conocimiento general (aún
> no hay fuentes sobre trading en `Fuentes/`). Conviene contrastarla con
> fuentes cuando se ingieran.

Implementación práctica: [[Proyectos/bot-trading/README|Proyecto bot-trading]].

## Características

### 1. Estrategia con ventaja demostrable
- Reglas explícitas y deterministas de entrada, salida y tamaño de posición.
- Ventaja estadística positiva **después** de comisiones, spread y deslizamiento.
- Robustez entre mercados, periodos y regímenes; si solo funciona con
  parámetros exactos, está sobreajustada.

### 2. Validación rigurosa
- Backtesting con datos de calidad, sin sesgo de anticipación ni de supervivencia.
- Validación walk-forward y fuera de muestra.
- Paper trading y luego capital pequeño antes de escalar.

### 3. Gestión de riesgo automática (lo más importante)
- Tamaño de posición por riesgo (p. ej. un 1 % del capital por operación).
- Stop-loss siempre, a ser posible colocado en el exchange.
- Límites de pérdida diaria y de drawdown máximo que detienen el bot.
- Control de apalancamiento, concentración y correlación.
- Kill switch manual y automático.

### 4. Ejecución fiable
- Reintentos y respeto de los límites de peticiones de la API.
- Idempotencia: no duplicar órdenes tras un corte de conexión.
- Reconciliación periódica con las posiciones reales.
- Manejo de órdenes parciales, rechazadas o canceladas.

### 5. Resiliencia operativa
- Servidor 24/7, estado persistente y reinicio automático.
- Modo seguro ante datos anómalos o API caída: no abrir posiciones.

### 6. Monitorización y alertas
- Logs, alertas (Telegram/email), panel de métricas y heartbeat externo.

### 7. Adaptación controlada
- Detectar cambios de régimen o desviaciones respecto al backtest y reducir
  tamaño o pausar; nunca cambiar reglas en vivo sin validar.

### 8. Seguridad
- Claves de API sin permiso de retirada y restringidas por IP; secretos fuera del código.

### 9. Sostenibilidad económica
- Que las ganancias cubran comisiones, servidor, datos e impuestos, y registro contable.

### 10. Ingeniería sana
- Arquitectura modular, tests, la misma lógica en backtest y en real, y configuración externa.

## Idea clave
Lo que hace autosuficiente a un bot no es que gane siempre, sino que
**sobreviva solo**: limita las pérdidas, se detiene ante lo inesperado, se
recupera de fallos y avisa cuando necesita a un humano. La rentabilidad la da
la estrategia; la supervivencia, el riesgo y la ingeniería.
