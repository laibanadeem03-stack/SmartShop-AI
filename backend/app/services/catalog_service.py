from ..errors import ApiError


class CatalogService:
    def __init__(self, repository):
        self.repository = repository

    def list_products(self, query):
        return self.repository.products(query)

    def product(self, identifier):
        result = self.repository.product(identifier)
        if result is None:
            raise ApiError(404, 'PRODUCT_NOT_FOUND', 'Product not found.')
        return result
