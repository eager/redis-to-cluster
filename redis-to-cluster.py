import re
import sys
import argparse

import redis
import pytool
import rediscluster


quiet = False  # verbose unless quiet logging global


def debug(msg):
    sys.stderr.write(msg + "\n")
    # sys.stderr.flush()


def connect_redis(kwargs):
    if kwargs['password'] is None:
        kwargs.pop('password')
    conn = redis.StrictRedis(**kwargs)
    return conn


def connect_redis_cluster(kwargs):
    if kwargs['password'] is None:
        kwargs.pop('password')
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
    format = ('<schema>://(:password)@<host>:<port>/(db) (exclude db number '
              'for cluster mode)')
    try:
        schema = re.search('^(.*)://', string).group(1)
        host = re.search('://(:.*@)*(.*):', string).group(2)
        port = re.search('://(:.*@)*.*:(.*)/', string).group(2)
    except Exception:
        raise argparse.ArgumentTypeError('incorrect format, should be: %s'
                                         % format)

    if schema == 'rediss':
        ssl = True
    else:
        ssl = False

    # Parse the database number from the connection string
    db = re.search(r':.*/(\d+$)', string)
    if db is not None and hasattr(db, 'group'):
        db = db.group(1)
    else:
        db = None
        debug('INFO: Using cluster mode for %s' % host)

    # Parse the password from the connection string
    password = re.search('://:(.*)@', string)
    if password is not None and hasattr(password, 'group'):
        password = password.group(1)
    else:
        password = None
        debug('INFO: No password set for %s' % host)

    return {'ssl': ssl,
            'password': password,
            'host': host,
            'port': port,
            'db': db}


def migrate_redis(source, destination):
    src = connect_to_redis(source)
    dst = connect_to_redis(destination)

    timer = pytool.time.Timer()
    count = 0
    errors = 0
    for key in src.keys('*'):
        count += 1
        ttl = src.ttl(key)

        # we handle TTL command returning -1 (no expire) or -2 (no key)
        if ttl < 0:
            ttl = 0
        debug("Dumping key: %s" % key)
        value = src.dump(key)
        debug("Restoring key: %s" % key)
        try:
            dst.restore(key, ttl * 1000, value, replace=True)
            count += 1
        except rediscluster.exceptions.ResponseError as e:
            errors += 1
            print("WARN: Failed to restore key: %s" % key)
            print("Error: " + str(e))
            pass
        if not count % 1000:
            print(f"Count: {count} Timer: {timer.elapsed}s")
    return


def run():
    parser = argparse.ArgumentParser(
        description="Simple script to migrate Redis database key data, in a "
        "non destructive way.")
    parser.add_argument('--source', '-s', required=True,
                        help="source Redis server / cluster")
    parser.add_argument('--destination', '-d', required=True,
                        help="designation Redis server / cluster")
    parser.add_argument("--quiet", "-q", action="store_true", help="do not "
                        "print name of keys copied, only errors")
    options = parser.parse_args()

    global quiet
    quiet = options.quiet

    migrate_redis(conn_string_type(options.source),
                  conn_string_type(options.destination))


if __name__ == '__main__':
    run()
