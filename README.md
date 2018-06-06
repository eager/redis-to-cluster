# redis-to-cluster
Simple script to migrate Redis database key data to Redis (or Elasticache) in cluster mode.

# How to use
* git clone git@github.com:u2mejc/redis-to-cluster.git
* virtualenv redis-to-cluster
* source redis-to-cluster/bin/activate
* pip install redis-py-cluster
* install -U git+git://github.com/andymccurdy/redis-py.git
* python redis-to-cluster.py

# Credit
Based on Github Gist [josegonzalez/redis_migrate.py](https://gist.github.com/josegonzalez/6049a72cb163337a18102743061dfcac), which is a fork of [iserko/redis_migrate.py](https://gist.github.com/iserko/9258373).
