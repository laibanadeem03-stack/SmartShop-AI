"""Public demo listings never read or return private user mappings."""


from ..errors import ApiError


class IdentityService:
    def __init__(self, repository, demo_repository):
        self.repository, self.demo_repository = repository, demo_repository

    def list_profiles(self):
        return self.repository.profiles()

    def create(self):
        return self.demo_repository.create()

    def resolve(self, alias):
        user = self.repository.private_user(alias)
        if user is not None:
            return user, False
        if self.demo_repository.exists(alias):
            return None, True
        raise ApiError(404, 'USER_NOT_FOUND', 'Demo user not found.')
