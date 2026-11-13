"""Deliberately local, single-worker launcher for the demo API."""
import uvicorn
import importlib
from threadpoolctl import threadpool_limits

if __name__ == '__main__':
    # Limits apply to already-loaded native libraries, so load the existing
    # numerical stack before entering the controller (no fitting occurs).
    for module in ('numpy','scipy.sparse','sklearn.feature_extraction.text'):
        importlib.import_module(module)
    with threadpool_limits(limits=1):
        uvicorn.run('backend.app.main:create_app',factory=True,
                    host='127.0.0.1',port=8000,workers=1,access_log=False)
