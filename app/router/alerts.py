"""Alerts REST endpoints."""

from fastapi import APIRouter, Depends, Request, status

from app.models.alert import (
    AlertEventResponse,
    AlertResponse,
    CreateAlertRequest,
    PriceUpdateRequest,
)
from app.services.alerts.service import AlertService

router = APIRouter(prefix="/alerts", tags=["alerts"])


def get_alert_service(request: Request) -> AlertService:
    return request.app.state.alert_service


@router.post("/evaluate", response_model=list[AlertEventResponse])
async def evaluate_price(
    payload: PriceUpdateRequest,
    service: AlertService = Depends(get_alert_service),
):
    """Feed a market price update; returns fired alert events."""
    events = await service.handle_price(payload.symbol, payload.price)
    return [AlertEventResponse.from_event(e) for e in events]


@router.get("", response_model=list[AlertResponse])
async def list_alerts(service: AlertService = Depends(get_alert_service)):
    return [AlertResponse.from_alert(a) for a in await service.list()]


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: CreateAlertRequest,
    service: AlertService = Depends(get_alert_service),
):
    alert = await service.create(payload)
    return AlertResponse.from_alert(alert)


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: str, service: AlertService = Depends(get_alert_service)):
    return AlertResponse.from_alert(await service.get(alert_id))


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(alert_id: str, service: AlertService = Depends(get_alert_service)):
    await service.delete(alert_id)


@router.post("/{alert_id}/enable", response_model=AlertResponse)
async def enable_alert(alert_id: str, service: AlertService = Depends(get_alert_service)):
    return AlertResponse.from_alert(await service.enable(alert_id))


@router.post("/{alert_id}/disable", response_model=AlertResponse)
async def disable_alert(alert_id: str, service: AlertService = Depends(get_alert_service)):
    return AlertResponse.from_alert(await service.disable(alert_id))