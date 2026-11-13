from fastapi import APIRouter, Request
from ..dependencies import require_ready
from ..schemas import HealthResponse

router = APIRouter(prefix='/health', tags=['health'])


@router.get('/live', response_model=HealthResponse, response_model_exclude_none=True)
def live():
    return {'status': 'alive'}


@router.get('/ready', response_model=HealthResponse)
def ready(request: Request):
    require_ready(request)
    return {'status': 'ready', 'model_version': 'hybrid-v1'}
