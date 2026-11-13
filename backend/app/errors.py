import logging
from uuid import uuid4
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from .config import ORIGIN

logger = logging.getLogger('smartshop.api')


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def error_response(request, status, code, message):
    request_id = getattr(request.state, 'request_id', uuid4().hex)
    return JSONResponse(status_code=status, content={'error': {
        'code': code, 'message': message, 'request_id': request_id}},
        headers={'X-Request-ID': request_id})


def register_handlers(app):
    @app.exception_handler(ApiError)
    async def known_error(request, exc):
        return error_response(request, exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic errors can contain submitted values and exception contexts.
        return error_response(request, 422, 'INVALID_REQUEST', 'Request parameters are invalid.')

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(request, exc.status_code,
                              'NOT_FOUND' if exc.status_code == 404 else 'HTTP_ERROR',
                              'Resource not found.' if exc.status_code == 404 else 'Request could not be completed.')

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        logger.error('Request failed (%s)', type(exc).__name__)
        response = error_response(request, 500, 'INTERNAL_ERROR', 'An unexpected error occurred.')
        # ServerErrorMiddleware sits outside CORSMiddleware. Preserve the same
        # explicit local-origin policy even for these sanitized 500 responses.
        if request.headers.get('origin') == ORIGIN:
            response.headers['Access-Control-Allow-Origin'] = ORIGIN
            response.headers['Vary'] = 'Origin'
        return response
