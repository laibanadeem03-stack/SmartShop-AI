"""Explicit public contracts: private database rows are never returned directly."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class PublicModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ProductQuery(PublicModel):
    page: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)
    q: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=300)


class ProductSummary(PublicModel):
    product_id: str
    title: str
    title_available: bool
    main_category: str | None
    categories: list[str]
    recommendation_eligible: bool


class ProductDetail(ProductSummary):
    training_interaction_count: int | None
    training_mean_rating: float | None


class ProductPage(PublicModel):
    items: list[ProductSummary]
    page: int
    page_size: int
    total: int


class DemoProfile(PublicModel):
    public_user_id: str
    label: str
    profile_type: Literal['dataset_backed']
    activity: Literal['light', 'moderate', 'active']


class DemoProfiles(PublicModel):
    items: list[DemoProfile]
    total: int


class HealthResponse(PublicModel):
    status: Literal['alive', 'ready']
    model_version: str | None = None


class ErrorDetail(PublicModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(PublicModel):
    error: ErrorDetail


ModelName = Literal['hybrid', 'count', 'cf', 'content']
ScoreType = Literal['normalized_weighted_rrf', 'positive_cosine_sum', 'cosine_similarity',
                    'training_interaction_count', 'fallback_zero']
Source = Literal['hybrid_both','cf_only','content_only','cf','content','count_popularity','popularity_fallback']


class RecommendationQuery(PublicModel):
    model: ModelName = 'hybrid'


class CreateDemoUser(PublicModel):
    pass


class NewDemoUser(PublicModel):
    public_user_id: str
    label: str
    profile_type: Literal['new_demo']


class RecommendationItem(PublicModel):
    rank: int = Field(ge=1, le=10)
    product: ProductSummary
    score: float = Field(ge=0, allow_inf_nan=False)
    score_type: ScoreType
    source: Source


class RecommendationResponse(PublicModel):
    batch_id: str
    public_user_id: str
    requested_model: ModelName
    model: ModelName
    model_version: str
    history_policy: Literal['training_snapshot']
    cold_start: bool
    returned_count: int
    personalized_count: int
    fallback_count: int
    items: list[RecommendationItem]


class SimilarItem(PublicModel):
    rank: int
    product: ProductSummary
    score: float = Field(gt=0, allow_inf_nan=False)
    score_type: Literal['cosine_similarity']


class SimilarResponse(PublicModel):
    product_id: str
    model: Literal['content']
    items: list[SimilarItem]


class SeedContribution(PublicModel):
    product: ProductSummary
    similarity: float = Field(gt=0, allow_inf_nan=False)


class CFSupport(PublicModel):
    seed_contributions: list[SeedContribution]
    total_seed_similarity: float = Field(gt=0, allow_inf_nan=False)


class SharedFeature(PublicModel):
    field: Literal['title','category']
    term: str
    dot_product_contribution: float = Field(gt=0, allow_inf_nan=False)


class ContentSupport(PublicModel):
    top_shared_features: list[SharedFeature]
    total_feature_contribution: float = Field(gt=0, allow_inf_nan=False)


class FusionEvidence(PublicModel):
    rank_constant: Literal[60]
    configured_cf_weight: float
    effective_cf_weight: float
    effective_content_weight: float
    cf_rank: int | None
    content_rank: int | None
    cf_rank_contribution: float
    content_rank_contribution: float


class CountEvidence(PublicModel):
    training_interaction_count: int = Field(ge=1)


class ExplanationResponse(PublicModel):
    batch_id: str
    product: ProductSummary
    model: ModelName
    source: Source
    ranking_score: float = Field(ge=0, allow_inf_nan=False)
    score_type: ScoreType
    reasons: list[str]
    cf_support: CFSupport | None = None
    content_support: ContentSupport | None = None
    fusion: FusionEvidence | None = None
    count_evidence: CountEvidence | None = None


class SegmentMetrics(PublicModel):
    segment: str
    evaluated_users: int
    recall_at_10: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    ndcg_at_10: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    catalog_coverage_at_10: float | None = Field(ge=0, le=1, allow_inf_nan=False)


class ModelPerformance(PublicModel):
    model: ModelName
    split: Literal['validation','test']
    segments: list[SegmentMetrics]
    fraction_users_personalized: float = Field(ge=0, le=1)
    fraction_fallback_slots: float = Field(ge=0, le=1)


class MetricsResponse(PublicModel):
    evaluation: str
    candidate_products: int
    serving_history_policy: Literal['training_snapshot']
    metrics_history_policy: str
    relevance: str
    default_model: ModelName
    models: list[ModelPerformance]
    limitations: list[str]
