"""Aggregates every v1 router into a single APIRouter mounted by `app.main`."""
from fastapi import APIRouter

from app.api.v1 import auth, dashboard, devices, events, incidents, network, phishing, playbooks

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(devices.router)
api_router.include_router(events.router)
api_router.include_router(phishing.router)
api_router.include_router(network.router)
api_router.include_router(dashboard.router)
api_router.include_router(incidents.router)
api_router.include_router(playbooks.router)
