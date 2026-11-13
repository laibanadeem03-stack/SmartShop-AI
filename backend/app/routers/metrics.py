from typing import Annotated
from fastapi import APIRouter, Depends
from ..dependencies import metrics_service
from ..schemas import MetricsResponse, ModelName
from ..services.metrics_service import MetricsService

router = APIRouter(prefix='/metrics', tags=['metrics'])
Service = Annotated[MetricsService, Depends(metrics_service)]


@router.get('/models', response_model=MetricsResponse)
def models(service: Service):
    return service.results()


@router.get('/models/{model}', response_model=MetricsResponse)
def model(model: ModelName, service: Service):
    return service.results(model)
