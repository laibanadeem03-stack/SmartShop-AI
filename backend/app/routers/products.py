from typing import Annotated
from fastapi import APIRouter, Depends, Path, Query
from ..dependencies import catalog_service
from ..schemas import ProductDetail, ProductPage, ProductQuery
from ..services.catalog_service import CatalogService

router = APIRouter(prefix='/products', tags=['products'])


@router.get('', response_model=ProductPage)
def products(query: Annotated[ProductQuery, Query()],
             service: Annotated[CatalogService, Depends(catalog_service)]):
    return service.list_products(query)


@router.get('/{product_id}', response_model=ProductDetail)
def product(product_id: Annotated[str, Path(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')],
            service: Annotated[CatalogService, Depends(catalog_service)]):
    return service.product(product_id)
