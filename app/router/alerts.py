"""Alerts REST endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.models.alert import (
    AlertEventResponse,
    AlertResponse,
    CreateAlertRequest,
    PriceUpdateRequest,
)
from app.services.alerts.service import AlertService
from app.services.notifications import InAppChannel

router = APIRouter(prefix="/alerts", tags=["alerts"])


def get_alert_service(request: Request) -> AlertService:
    return request.app.state.alert_service


def get_event_log(request: Request) -> InAppChannel:
    """The in-app channel's event buffer (newest-first)."""
    channels = request.app.state.notification_channels
    channel = channels.get("in_app")
    if not isinstance(channel, InAppChannel):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="in-app event log unavailable",
        )
    return channel


@router.get("/events", response_model=list[AlertEventResponse])
async def list_events(
    limit: int = Query(default=50, ge=1, le=200),
    events: InAppChannel = Depends(get_event_log),
):
    """Recent fired-alert events, newest first (works no matter who poll_refreshes)."""
    return [AlertEventResponse.from_event(e) for e in events.recent(limit)]


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


@router.put("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: str,
    payload: CreateAlertRequest,
    service: AlertService = Depends(get_alert_service),
):
    return AlertResponse.from_alert(await service.update(alert_id, payload))


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(alert_id: str, service: AlertService = Depends(get_alert_service)):
    await service.delete(alert_id)


@router.post("/{alert_id}/enable", response_model=AlertResponse)
async def enable_alert(alert_id: str, service: AlertService = Depends(get_alert_service)):
    return AlertResponse.from_alert(await service.enable(alert_id))


@router.post("/{alert_id}/disable", response_model=AlertResponse)
async def disable_alert(alert_id: str, service: AlertService = Depends(get_alert_service)):
    return AlertResponse.from_alert(await service.disable(alert_id))