#!/usr/bin/env python
import argparse
import re
import redis
import rediscluster

quiet = False # verbose unless quiet logging global
replace = False # Replace keys global

def connect_redis(kwargs):
    if kwargs['password'] is None: kwargs.pop('password')
    conn = redis.StrictRedis(**kwargs)
    return conn

def connect_redis_cluster(kwargs):
    if kwargs['password'] is None: kwargs.pop('password')
    kwargs.pop('db')
    kwargs['skip_full_coverage_check'] = True
    conn = rediscluster.StrictRedisCluster(**kwargs)
    return conn

def connect_to_redis(kwargs):
    if kwargs['db'] is None:
        conn = connect_redis_cluster(kwargs)
    else:
        conn = connect_redis(kwargs)
    return conn

def conn_string_type(string):
    # http://www.iana.org/assignments/uri-schemes/prov/redis
    format = '<schema>://(:password)@<host>:<port>/(db) (exclude db number for cluster mode)'
    try:
        schema = re.search('^(.*)://', string).group(1) # schema
        host = re.search('://(:.*@)*(.*):', string).group(2) # host
        port = re.search('://(:.*@)*.*:(.*)/', string).group(2) # port
    except:
        raise argparse.ArgumentTypeError('incorrect format, should be: %s' % format)

    if schema == 'rediss':
        ssl = True
    else:
        ssl = False

    db = re.search(':.*/(\d+$)', string) # database number
    if db is not None and hasattr(db, 'group'):
        db = db.group(1)
    else:
        db = None
        if not quiet: print('INFO: Using cluster mode for %s' % host)

    password = re.search('://:(.*)@', string) # password
    if password is not None and hasattr(password, 'group'):
        password = password.group(1)
    else:
        password = None
        if not quiet: print('INFO: No password set for %s' % host)

    return {'ssl': ssl,
            'password': password,
            'host': host,
            'port': port,
            'db': db}

def migrate_redis(source, destination):
    src = connect_to_redis(source)
    dst = connect_to_redis(destination)
    src_dump_pipeline = src.pipeline()
    src_ttl_pipeline = src.pipeline()
    src_dbsize = src.dbsize()
    dst_pipeline = dst.pipeline()
    dst_keys = []
    pipeline_count = 0

    if not quiet: print "INFO: Migrating %s keys from source" % src_dbsize

    src_keys = src.keys('*')
    for key in src_keys:
        # make verbose # if not quiet: print "Adding key to dump pipeline: %s" % key
        if src_dbsize < 100: print('pipeline_count vs src_dbsize', pipeline_count, src_dbsize)
        if pipeline_count == 100000 or src_dbsize == 1:
            dst_keys.append(key)
            src_dump_pipeline.dump(key)
            src_ttl_pipeline.pttl(key)
            pipeline_count += 1
            src_dbsize -= 1

            if not quiet: print "\nINFO: Adding dumps to restore pipeline...\n"
            dst_values = src_dump_pipeline.execute()
            dst_ttl = src_ttl_pipeline.execute()

            dst_values_dict = dict(zip(dst_keys, dst_values))
            dst_ttl_dict = dict(zip(dst_keys, dst_ttl))
            for for_key in dst_values_dict:
                #dst.restore(key, ttl * 1000, value, replace=True)
                if dst_ttl_dict[for_key] < 0: dst_ttl_dict[for_key] = 0 # TTL must be 0 (no TTL)
                dst_pipeline.restore(for_key,
                                     int(dst_ttl_dict[for_key]),
                                     dst_values_dict[for_key],
                                     replace=replace)

            if not quiet: print "\nINFO: Restoring keys... (This may take some time)\n"
            try:
                results = dst_pipeline.execute()
            except rediscluster.exceptions.ResponseError as e:
                print "WARN: Failed to restore keys:"
                print ("Error result: " + str(e))
                pass
            if not quiet: print "\nINFO: %s keys remaining to transfer\n" % src_dbsize
            # Clean up here
            src_dump_pipeline.reset()
            src_ttl_pipeline.reset()
            dst_pipeline.reset()
            pipeline_count = 0
            dst_keys = []

        else:
            dst_keys.append(key)
            #value = src.dump(key)
            src_dump_pipeline.dump(key)
            src_ttl_pipeline.pttl(key)
            #src_dump_pipeline.ttl(key)
            pipeline_count += 1
            src_dbsize -= 1


    return

def run():
    parser = argparse.ArgumentParser()
    parser = argparse.ArgumentParser(description='Simple script to migrate Redis database key data, in a non destructive way.')
    parser.add_argument('--source', '-s', required=True, help="source Redis server / cluster")
    parser.add_argument('--destination', '-d', required=True, help="designation Redis server / cluster")
    parser.add_argument("--quiet", "-q", action="store_true", help="do not print name of keys copied, only errors")
    parser.add_argument("--replace", "-r", action="store_true", help="replace keys already existing on destination")
    options = parser.parse_args()

    global quiet
    quiet = options.quiet
    global replace
    replace = options.replace

    migrate_redis(conn_string_type(options.source), conn_string_type(options.destination))

if __name__ == '__main__':
    run()
