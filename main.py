import re
import sys
import queue
import logging
import argparse
import threading

import redis
import pytool
import rediscluster


quiet = False  # verbose unless quiet logging global


def debug(msg):
    if not quiet:
        sys.stderr.write(msg + "\n")
    # sys.stderr.flush()


def connect_redis(conn):
    """ Return a redis client. """
    # Don't pass empty password to the client
    if not conn.get('password', None):
        conn.pop('password', None)

    return redis.StrictRedis(**conn)


def connect_redis_cluster(conn):
    """ Return a Redis cluster client. """
    # Don't pass empty password to the client
    if not conn.get('password', None):
        conn.pop('password', None)

    # Add option to avoid this check
    conn['skip_full_coverage_check'] = True

    return rediscluster.StrictRedisCluster(**conn)


def get_client(conn):
    """
    Return a Redis client object based on the *conn* dictionary.

    :param dict conn: Dictionary of connection info as returned by *parse_url*.

    """
    # No database indicates a cluster connection
    if not conn.get('db', None):
        conn.pop('db', None)
        return connect_redis_cluster(conn)

    # Otherwise it's a regular redis connection
    return connect_redis(conn)


def parse_url(url):
    """
    Return *url* parsed into a dictionary for consumption by the Redis client
    objects.

    :param str url: URL connection string

    """
    # Expected URL format string (for error messages)
    # http://www.iana.org/assignments/uri-schemes/prov/redis
    expected = ('<schema>://(:password)@<host>:<port>/(db) (exclude db number '
                'for cluster mode)')

    # Make sure we can parse the key bits of the URL
    try:
        schema = re.search('^(.*)://', url).group(1)
        host = re.search('://(:.*@)*(.*):', url).group(2)
        port = re.search('://(:.*@)*.*:(.*)/', url).group(2)
    except Exception:
        raise argparse.ArgumentTypeError('incorrect format, should be: %s'
                                         % expected)

    # Toggle SSL if we have a secure schema
    ssl = (schema == 'rediss')

    # Parse the database number from the connection string
    db = re.search(r':.*/(\d+$)', url)
    if db is None:
        debug('INFO: Using cluster mode for %s' % host)
    else:
        db = db.group(1)

    # Parse the password from the connection string
    password = re.search('://:(.*)@', url)
    if password is None:
        debug('INFO: No password set for %s' % host)
    else:
        password = password.group(1)

    return {'ssl': ssl,
            'password': password,
            'host': host,
            'port': port,
            'db': db}


@pytool.lang.singleton
class Logger:
    """ Logging wrapper for easy use in threads. """
    def __init__(self, level=logging.INFO, filename=None):
        # Configure global logging
        logging.basicConfig(
            format="%(asctime)s [%(levelname)s] %(message)s",
            level=level, filename=filename)
        # Get a logger for us to use
        self.logger = logging.getLogger('redis-migrate')
        self.logger.setLevel(level)
        # Map logger attributes up
        self.info = self.logger.info
        self.debug = self.logger.debug
        self.error = self.logger.error


@pytool.lang.singleton
class Metrics:
    def __init__(self, prefix, total, frequency=1000):
        self.prefix = prefix
        self.total = total
        self.frequency = frequency
        self.lock = threading.Lock()
        self.copied = 0
        self.errored = 0
        self.timer = pytool.time.Timer()

    def count(self):
        with self.lock:
            self.copied += 1

            if not self.copied % self.frequency:
                self.output_stats()

    def error(self):
        with self.lock:
            self.errored += 1

    def output_stats(self):
        """ Prints stats to logging. """
        elapsed = self.timer.elapsed
        count = self.copied + self.errored
        total = self.total
        # Time per key in milliseconds
        avg = round(elapsed / count * 1000, 3)
        # Time remaining in seconds
        remaining = 1.0 * elapsed / count * (total - count)
        # Time remaining in minutes
        remaining = round(remaining / 60.0, 1)
        # Time taken in minutes
        elapsed = round(elapsed / 60.0, 1)

        sys.stderr.write(f"{self.prefix}: {avg}ms, {elapsed}min passed, "
                         f"{remaining}min remaining.")


class Worker(threading.Thread):
    def __init__(self, key_queue, src, dest, log):
        self.queue = key_queue
        self.src = src
        self.dest = dest
        self.log = log
        super().__init__()

    def run(self):
        """ Consume the *key_queue*, migrating keys. """
        metrics = Metrics()

        count = 0
        while not self.queue.empty():
            count += 1
            try:
                key = self.queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                self.copy_key(key)
                metrics.count()
            except Exception as err:
                self.log.error(f"Error for key '{key}'")
                self.log.debug(err, exc_info=True)
                metrics.error()

        self.log.info(f"Thread completed. {count} keys processed.")

    def copy_key(self, key):
        """ Copy *key* from the source to the destination. """
        # Get the TTL for the key
        ttl = self.src.ttl(key)

        # -2 means the key doesn't actually exist and is a lie
        if ttl == -2:
            self.log.debug(f"TTL -2: {key}")
            return

        # -1 means the key has no expiration and we set it to 90 days
        if ttl == -1:
            self.log.debug(f"TTL -1: {key}")
            ttl = 60*60*24*90

        # restore uses TTL in ms
        ttl = ttl * 1000

        # Get the original value
        value = self.src.dump(key)

        # Set the key on our destination
        self.dst.restore(key, ttl, value, replace=True)


class Migrate:
    # Redis connection objects
    _src = None
    _dest = None

    def __init__(self, prefix, source, destination, workers=10):
        self.prefix = prefix
        self.source_url = source
        self.dest_url = destination
        self.workers = workers
        self.queue = queue.Queue()
        self.log = Logger()

    def run(self):
        self.log.info("Starting migration.")

        # Get all the keys and store them
        timer = pytool.time.Timer()
        self.src_keys = self.src.keys(self.prefix)
        self.log.info(f"Retrieve source keys: {timer.mark()}s")

        timer = pytool.time.Timer()
        self.dest_keys = self.dest.keys(self.prefix)
        self.log.info(f"Retrieve destination keys: {timer.mark()}s")

        self.log.info(f"Time to retrieve keys: {timer.elapsed}s")

        # Find the difference in the destination keys
        timer.mark()
        self.keys = set(self.src_keys) - set(self.dest_keys)
        self.log.info(f"Time to compute set: {timer.mark()}s")
        self.log.info(f"Keys to process: {len(self.keys)}")

        # Populate the threadsafe queue with keys
        for key in self.keys:
            self.queue.put(key)

        self.log.info(f"Time to populate queue: {timer.mark()}s")

        # Create metrics
        self.metrics = Metrics(self.prefix, len(self.keys))

        # Create worker threadpool
        timer.mark()
        self.log.debug(f"Creating {self.workers} workers.")
        self.pool = [Worker(self.queue, self.src, self.dest, self.log)
                     for i in range(self.workers)]
        self.log.info(f"Time to create workers: {timer.mark()}s")

        # Start all the worker threads
        for worker in self.pool:
            worker.start()

        # Wait for workers to finish
        for worker in self.pool:
            worker.join()

        self.log.info("Copy time: {timer.mark()}s")
        self.log.info("Total time taken: {timer.elapsed}s")

    @property
    def src(self):
        """ Return a cached client connection object. """
        if self._src:
            return self._src

        # Parse and create a new client
        conn = parse_url(self.source_url)
        client = get_client(conn)
        self._src = client
        return self._src

    @property
    def dest(self):
        """ Return a cached client connection object. """
        if self._dest:
            return self._dest

        # Parse and create a new client
        conn = parse_url(self.source_url)
        client = get_client(conn)
        self._dest = client
        return self._dest


class Main(pytool.cmd.Command):
    def set_opts(self):
        self.describe("Simple script to migrate Redis database key data, in a "
                      "non destructive way.")
        self.opt('--source', '-s', required=True, help="source Redis server / "
                 "cluster")
        self.opt('--destination', '-d', required=True, help="destination "
                 "Redis server / cluster")
        self.opt('--workers', '-w', default=10, help="Number of workers")
        self.opt('--logging', '-l', default='info',
                 choices=['debug', 'info', 'error'],
                 help="Set log level")
        self.opt('--logfile', '-f', type=str, help="Log to file")
        self.opt('--prefix', '-p', default="*", help="source key prefix ")

    def run(self):
        self.log = Logger(getattr(logging, self.args.logging.upper()),
                          self.args.logfile)
        self.log.debug("Logging configured successfully.")

        migrate = Migrate(self.args.prefix, self.args.source,
                          self.args.destination, self.args.workers)
        self.log.debug("Created migration runner.")
        migrate.run()


if __name__ == '__main__':
    Main().start(sys.argv[1:])
