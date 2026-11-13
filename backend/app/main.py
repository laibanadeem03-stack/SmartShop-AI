"""Application factory. No data preparation or training happens on startup."""
from contextlib import asynccontextmanager
import logging
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import ORIGIN, Settings, local_path
from .errors import register_handlers
from .repositories.sqlite_repository import CatalogRepository
from .repositories.demo_repository import DemoRepository
from .routers import health, metrics, products, recommendations, users
from .schemas import ErrorResponse
from .services.catalog_service import CatalogService
from .services.identity_service import IdentityService
from .services.model_registry import load_registry, sha256
from .services.batch_cache import BatchCache
from .services.metrics_service import MetricsService
from .services.recommendation_service import RecommendationService

logger = logging.getLogger('smartshop.api')


def create_app(settings=None, registry_loader=load_registry):
    @asynccontextmanager
    async def lifespan(app):
        started = time.perf_counter()
        app.state.ready = False
        app.state.registry = None
        try:
            config = settings if settings is not None else Settings.from_environment()
            database = local_path(config.database)
            metadata = local_path(config.metadata)
            if sha256(database) != config.database_sha256 or sha256(metadata) != config.metadata_sha256:
                raise ValueError('Application source checksum mismatch')
            registry = registry_loader(config)
            repository = CatalogRepository(database)
            repository.validate(config, registry)
            demo_repository = DemoRepository(config.runtime_directory, config.maximum_demo_users)
            cache = BatchCache(config.batch_capacity,config.batch_ttl_seconds)
            app.state.registry = registry
            app.state.catalog = CatalogService(repository)
            app.state.identities = IdentityService(repository,demo_repository)
            app.state.recommendations = RecommendationService(registry,repository,app.state.identities,cache)
            app.state.metrics = MetricsService(registry.performance)
            app.state.ready = True
        except Exception as exc:
            # No traceback or path/identifier-rich exception text in normal logs.
            logger.error('Startup validation failed (%s)', type(exc).__name__)
        app.state.startup_seconds = time.perf_counter()-started
        try:
            yield
        finally:
            app.state.ready = False
            app.state.registry = None
            app.state.catalog = None
            app.state.identities = None
            if getattr(app.state,'recommendations',None) is not None:
                app.state.recommendations.cache.clear()
            app.state.recommendations = None
            app.state.metrics = None

    app = FastAPI(title='SmartShop-AI', version='0.2.0', lifespan=lifespan,
                  responses={code: {'model': ErrorResponse} for code in (404, 409, 422, 500, 503)})
    app.state.ready = False

    @app.middleware('http')
    async def request_id(request, call_next):
        request.state.request_id = uuid4().hex
        response = await call_next(request)
        response.headers['X-Request-ID'] = request.state.request_id
        return response

    app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN],
                       allow_methods=['GET','POST'], allow_headers=['Accept','Content-Type'], allow_credentials=False)
    register_handlers(app)
    for router in (health.router, products.router, users.router, recommendations.router, metrics.router):
        app.include_router(router, prefix='/api/v1')
    return app
