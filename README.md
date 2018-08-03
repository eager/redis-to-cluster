# redis-to-cluster
A simple script to migrate Redis database key data to Redis (or Elasticache) in cluster mode. 

Supports:
- Reids
- Redis Cluster Mode
- SSL (aka rediss://)
- AUTH passwords

# Redis URLs
You must format your URL appropriately, per http://www.iana.org/assignments/uri-schemes/prov/redis

format = `<schema>://(:password)@<host>:<port>/(db) (exclude db number for cluster mode)`

# How to use
```
git clone git@github.com:u2mejc/redis-to-cluster.git
virtualenv redis-to-cluster
source redis-to-cluster/bin/activate
pip install -r requirments.txt
python redis-to-cluster.py -h
python redis-to-cluster.py -s redis://<redis_hostname>:6379/0 -d rediss://(:password)@<redis_cluster>:6379/
```

# Credit
Based on Github Gist [josegonzalez/redis_migrate.py](https://gist.github.com/josegonzalez/6049a72cb163337a18102743061dfcac), which is a fork of [iserko/redis_migrate.py](https://gist.github.com/iserko/9258373).
