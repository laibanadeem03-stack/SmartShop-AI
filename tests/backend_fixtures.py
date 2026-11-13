"""Synthetic fixtures contain no real dataset identities or metadata."""
import hashlib
import json
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

from backend.app.config import LOCAL, Settings
from backend.app.services.model_registry import ModelRegistry, sha256
from scripts.prepare_application_data import prepare_database
import numpy as np
from scipy import sparse
import content_tfidf
import hybrid_ranker
import item_cf


def fixture():
    LOCAL.mkdir(exist_ok=True)
    temp = tempfile.TemporaryDirectory(prefix='backend-test-',dir=LOCAL)
    directory = Path(temp.name)
    records = {
        'ITEM01':{'parent_asin':'ITEM01','title':'Phone ZX-42 5G 100%','main_category':'Accessories','categories':['Cases','Cases']},
        'ITEM02':{'parent_asin':'ITEM02','title':'USB-C Cable','main_category':None,'categories':['Cables']},
        'ITEM03':{'parent_asin':'ITEM03','title':'!!!','main_category':'Accessories','categories':['Cases']},
        'ITEM04':{'parent_asin':'ITEM04','title':'Outside training','main_category':None,'categories':[]},
    }
    metadata = directory/'metadata.jsonl'
    metadata.write_text(''.join(json.dumps(r)+'\n' for r in records.values()),encoding='utf-8')
    seen = {f'PRIVATE_SYNTHETIC_USER_{i}':{'ITEM01' if i%2==0 else 'ITEM02'} for i in range(12)}
    snapshot={'seen':seen,'user_counts':{u:(i%3)*2+1 for i,u in enumerate(seen)},
              'items':{p:{'count':12,'rating_sum':48} for p in ('ITEM01','ITEM02','ITEM03')}}
    users,items=sorted(seen),sorted(snapshot['items'])
    positive=sparse.csr_matrix(np.array([[int('ITEM01' in seen[u]),int('ITEM02' in seen[u]),0] for u in users],dtype=np.float32))
    features=sparse.csr_matrix(np.array([[1,0],[0.8,0.6],[0,0]],dtype=np.float32))
    graph=sparse.csr_matrix(np.array([[0,0.5,0],[0.4,0,0],[0,0,0]],dtype=np.float32))
    cb=content_tfidf.ContentRecommender(positive,users,items,features,snapshot)
    cf=item_cf.ItemRecommender(positive,users,items,graph,snapshot)
    model=hybrid_ranker.HybridRecommender(cf,cb,0.5)
    model.feature_names=[('title','phone'),('category','cable')]
    performance={'evaluation':'synthetic','candidate_products':3,'serving_history_policy':'training_snapshot',
                 'metrics_history_policy':'synthetic','relevance':'ratings_4_or_5','default_model':'hybrid','limitations':[],
                 'models':[{'model':m,'split':s,'segments':[{'segment':'overall','evaluated_users':1,
                            'recall_at_10':0.5,'ndcg_at_10':0.25,'catalog_coverage_at_10':1.0}],
                            'fraction_users_personalized':0.0,'fraction_fallback_slots':1.0}
                           for m in ('count','cf','content','hybrid') for s in ('validation','test')]}
    registry=ModelRegistry(model,'synthetic-training','synthetic-manifest',threading.Lock(),performance)
    db=directory/'app.sqlite3'
    prepare_database(db,records,registry,sha256(metadata),b'x'*32)
    settings=Settings(database=db,database_sha256=sha256(db),metadata=metadata,
                      metadata_sha256=sha256(metadata),expected_products=4,expected_eligible=3,
                      runtime_directory=directory/'runtime')
    return temp,settings,registry,records
