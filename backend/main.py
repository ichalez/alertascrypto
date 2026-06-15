"""API FastAPI + arranque del monitor de fondo + servido del frontend (PWA)."""
import os
import asyncio
import logging

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import store, notify
from .monitor import run_monitor, send_telegram_msg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("app")

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = FastAPI(title="alertascrypto")


@app.on_event("startup")
async def _startup():
    os.makedirs(store.DATA_DIR, exist_ok=True)
    store.ensure_vapid()
    store.get_config()  # crea config por defecto si no existe
    asyncio.create_task(run_monitor())
    log.info("Monitor arrancado")


# ----------------------- API -----------------------
@app.get("/api/state")
async def api_state():
    return store.STATE


@app.get("/api/config")
async def api_get_config():
    return store.get_config()


@app.put("/api/config")
async def api_put_config(request: Request):
    body = await request.json()
    cfg = store.get_config()
    # merge superficial de claves conocidas (no confiar ciegamente en el cliente)
    for key in ("running", "poll_seconds", "interval", "rsi_period",
                "atr_period", "stop_atr_mult", "rr_ratio",
                "mtf_filter", "mtf_interval", "schedule", "channels", "telegram"):
        if key in body:
            cfg[key] = body[key]
    if "assets" in body:
        for sym, acfg in body["assets"].items():
            if sym in cfg["assets"]:
                cfg["assets"][sym].update(acfg)
    store.save_config(cfg)
    return cfg


@app.get("/api/history")
async def api_history():
    return store.get_history()


@app.delete("/api/history")
async def api_clear_history():
    store.clear_history()
    return {"ok": True}


@app.post("/api/test")
async def api_test():
    cfg = store.get_config()
    results = {}
    async with httpx.AsyncClient() as client:
        tg = cfg.get("telegram", {})
        ok, msg = await notify.send_telegram(
            client, tg.get("token"), tg.get("chat_id"),
            "🔔 Prueba de alertascrypto — Telegram conectado correctamente.")
        results["telegram"] = {"ok": ok, "detail": msg}
    sent = await asyncio.to_thread(
        notify.send_push, "🔔 alertascrypto", "Notificaciones push activas.", "test")
    results["push"] = {"sent": sent}
    return results


@app.get("/api/push/key")
async def api_push_key():
    return {"publicKey": store.vapid_public_key()}


@app.post("/api/push/subscribe")
async def api_push_subscribe(request: Request):
    sub = await request.json()
    store.add_sub(sub)
    return {"ok": True}


@app.post("/api/push/unsubscribe")
async def api_push_unsubscribe(request: Request):
    body = await request.json()
    store.remove_sub(body.get("endpoint"))
    return {"ok": True}


# ----------------------- Frontend (PWA) -----------------------
# Se monta al final para que /api/* tenga prioridad
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
