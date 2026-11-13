from typing import Annotated
from fastapi import APIRouter, Depends
from ..dependencies import identity_service
from ..schemas import CreateDemoUser, DemoProfiles, NewDemoUser
from ..services.identity_service import IdentityService

router = APIRouter(prefix='/demo', tags=['demo'])


@router.get('/profiles', response_model=DemoProfiles)
def profiles(service: Annotated[IdentityService, Depends(identity_service)]):
    return service.list_profiles()


@router.post('/users', response_model=NewDemoUser,status_code=201)
def new_user(body: CreateDemoUser, service: Annotated[IdentityService, Depends(identity_service)]):
    return service.create()
