from typing import Annotated
from fastapi import APIRouter, Depends, Path, Query

from ..dependencies import recommendation_service
from ..schemas import ExplanationResponse, RecommendationQuery, RecommendationResponse, SimilarResponse
from ..services.recommendation_service import RecommendationService

router = APIRouter(tags=['recommendations'])
Service = Annotated[RecommendationService, Depends(recommendation_service)]
Identifier = Annotated[str, Path(min_length=1,max_length=64,pattern=r'^[A-Za-z0-9_-]+$')]


@router.get('/users/{public_user_id}/recommendations', response_model=RecommendationResponse)
def recommend(public_user_id: Identifier, query: Annotated[RecommendationQuery, Query()], service: Service):
    return service.recommend(public_user_id,query.model)


@router.get('/products/{product_id}/similar', response_model=SimilarResponse)
def similar(product_id: Identifier, service: Service):
    return service.similar(product_id)


@router.get('/recommendations/{batch_id}/items/{product_id}/explanation',
            response_model=ExplanationResponse,response_model_exclude_unset=True)
def explain(batch_id: Identifier, product_id: Identifier, service: Service):
    return service.explain(batch_id,product_id)
