from fastapi import Request
from .errors import ApiError


def require_ready(request: Request):
    if not request.app.state.ready:
        raise ApiError(503, 'NOT_READY', 'Application resources are unavailable.')


def catalog_service(request: Request):
    require_ready(request)
    return request.app.state.catalog


def identity_service(request: Request):
    require_ready(request)
    return request.app.state.identities


def recommendation_service(request: Request):
    require_ready(request)
    return request.app.state.recommendations


def metrics_service(request: Request):
    require_ready(request)
    return request.app.state.metrics
