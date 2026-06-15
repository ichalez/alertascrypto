# alertascrypto

Panel de alarmas RSI para scalping de cripto. Un proceso de fondo vigila BTC, ETH,
SOL, AAVE, AVAX, ADA y ATOM en 5 minutos, calcula el RSI-14 y avisa por **Telegram**
y **notificaciones push** cuando hay sobreventa/sobrecompra. La web es un panel
instalable (PWA) pensado para el móvil.

> Quantfury no tiene API: la app **no ejecuta operaciones**, solo te avisa.
> Tú operas a mano cuando llega la señal. Los datos de RSI vienen de Binance (público,
> gratis); para BTC/ETH y demás son prácticamente idénticos a los de Quantfury.

## Qué detecta

Por cada activo puedes activar de forma independiente:

- **Entrada en zona** — el RSI cruza a sobreventa (≤ umbral) o sobrecompra (≥ umbral).
- **Giro en zona** — está en zona extrema y el RSI empieza a girar (mejor entrada).
- **Salida de zona** — el RSI sale de la zona extrema (evita cuchillos cayendo).
- **Divergencia** — precio hace nuevo extremo pero el RSI no (señal de calidad).

Extras: umbrales por activo, silencio entre avisos (cooldown), filtro de tendencia
con temporalidad mayor (15m/1h/4h) y horario silencioso nocturno.

## Despliegue en el VPS (217.154.191.35)

```bash
# dentro de la carpeta alertascrypto
docker compose up -d --build
```

El panel queda en `http://217.154.191.35:8000`. La configuración y el historial se
guardan en `./data` (persisten entre reinicios).

### Telegram

1. Crea un bot con [@BotFather](https://t.me/BotFather) y copia el token (o reutiliza el que ya tienes).
2. Escribe a [@userinfobot](https://t.me/userinfobot) para conocer tu chat ID.
3. Pégalos en **Ajustes → Telegram** y pulsa **Enviar prueba**.

### Notificaciones push en el móvil

1. Abre el panel en el móvil y añádelo a la pantalla de inicio (PWA).
2. En **Ajustes → Avisos**, pulsa **Activar push en este móvil** y acepta el permiso.
   Las claves VAPID se generan solas en el primer arranque (en `./data`).

> El push del navegador requiere HTTPS (salvo en `localhost`). Si lo sirves por IP en
> claro, usa Telegram para los avisos, o pon un proxy con certificado (Caddy/Nginx) o
> un dominio detrás de tu Coolify/Easypanel.

## Notas

- Si Binance está geobloqueado en tu VPS, define `DATA_BASE` con otro endpoint compatible
  con `/api/v3/klines`.
- La zona horaria por defecto es `Europe/Madrid` (afecta al horario silencioso).
- La vela en formación se descarta siempre, para que el RSI no "repinte".
