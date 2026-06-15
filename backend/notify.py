"""Canales de notificación: Telegram (fiable, base) y Web Push (PWA)."""
import json
import logging

import httpx

from . import store

log = logging.getLogger("notify")


async def send_telegram(client, token, chat_id, text):
    if not token or not chat_id:
        return False, "Falta token o chat_id de Telegram"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = await client.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        r.raise_for_status()
        return True, "ok"
    except Exception as e:  # noqa: BLE001
        log.error("Telegram fallo: %s", e)
        return False, str(e)


def send_push(title, body, tag="rsi"):
    """Web Push a todas las suscripciones. Síncrono (pywebpush no es async)."""
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        log.warning("pywebpush no instalado; push desactivado")
        return 0

    subs = store.get_subs()
    if not subs:
        return 0
    with open(store.VAPID_PRIV_PATH) as f:
        priv = f.read()
    payload = json.dumps({"title": title, "body": body, "tag": tag})
    sent = 0
    for sub in list(subs):
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=priv,
                vapid_claims={"sub": "mailto:alertas@alertascrypto.local"},
            )
            sent += 1
        except WebPushException as e:  # noqa: PERF203
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):  # suscripción muerta -> limpiar
                store.remove_sub(sub.get("endpoint"))
            else:
                log.error("Push fallo: %s", e)
        except Exception as e:  # noqa: BLE001
            log.error("Push error: %s", e)
    return sent
