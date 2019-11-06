import re
import sys
import time
import queue
import logging
import argparse
import threading

import redis
import pytool
import rediscluster


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
        raise argparse.ArgumentTypeError(f'URL format: {expected}')

    # Toggle SSL if we have a secure schema
    ssl = (schema == 'rediss')

    # Parse the database number from the connection string
    db = re.search(r':.*/(\d+$)', url)
    if db is None:
        Logger().info(f'Using cluster mode for {host}')
    else:
        db = db.group(1)

    # Parse the password from the connection string
    password = re.search('://:(.*)@', url)
    if password is None:
        Logger().info(f'No password set for {host}')
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
    def __init__(self, prefix, total, frequency=25000):
        self.prefix = prefix
        self.total = total
        self.frequency = frequency
        self.lock = threading.Lock()
        self.copied = 0
        self.errored = 0
        self.log = Logger()
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
        elapsed = self.timer.elapsed.total_seconds()
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

        self.log.info(f"{self.prefix}: {avg}ms avg, {elapsed}min passed, "
                      f"{remaining}min remaining. ({count:,}/{total:,})")


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
            # self.log.debug(f"TTL -2: {key}")
            return

        # -1 means the key has no expiration and we set it to 90 days
        if ttl == -1:
            # self.log.debug(f"TTL -1: {key}")
            ttl = 60*60*24*90

        # restore uses TTL in ms
        ttl = ttl * 1000

        # Get the original value
        value = self.src.dump(key)

        # Set the key on our destination
        self.dest.restore(key, ttl, value, replace=True)


class Migrate:
    # Redis connection objects
    _src = None
    _dest = None

    def __init__(self, prefix, source, destination, workers=10,
                 overwrite=False):
        self.prefix = prefix
        self.source_url = source
        self.dest_url = destination
        self.workers = workers
        self.overwrite = overwrite
        self.queue = queue.Queue()
        self.log = Logger()
        self.src_keys = set()
        self.dest_keys = set()

    def run(self):
        self.log.info("Starting migration.")

        # Get all the keys and store them
        timer = pytool.time.Timer()

        # Retrieve source keys in a thread for parallelism
        get_src = threading.Thread(target=self.get_src_keys)
        get_src.start()

        if not self.overwrite:
            # Retrieve destination keys in a Thread
            get_dest = threading.Thread(target=self.get_dest_keys)
            get_dest.start()
            get_dest.join()

        # Wait for source retrieval to finish
        get_src.join()

        self.log.info(f"Time to retrieve keys: {timer.elapsed}")

        # Find the difference in the destination keys
        timer.mark()
        self.keys = set(self.src_keys) - set(self.dest_keys)
        self.log.debug(f"Time to compute set: {timer.mark()}")
        self.log.info(f"Keys to process: {len(self.keys):,}")
        self.log.info("Populating queue.")

        # Populate the threadsafe queue with keys
        for key in self.keys:
            self.queue.put(key)

        self.log.debug(f"Time to populate queue: {timer.mark()}")
        self.log.debug(f"Keys in queue: {self.queue.qsize():,}")

        # Create metrics
        self.metrics = Metrics(self.prefix, len(self.keys))

        # Create worker threadpool
        timer.mark()
        self.log.debug(f"Creating {self.workers} workers.")
        self.pool = [Worker(self.queue, self.src, self.dest, self.log)
                     for i in range(self.workers)]
        self.log.debug(f"Time to create workers: {timer.mark()}")

        # Start all the worker threads
        self.log.info("Starting workers.")
        for worker in self.pool:
            worker.start()

        self.log.info(f"Startup time: {timer.elapsed}")

        # Wait for workers to finish
        self.log.info("Processing.")
        for worker in self.pool:
            worker.join()

        self.log.info(f"Copy time: {timer.mark()}")
        self.log.info(f"Total time taken: {timer.elapsed}")
        self.log.info(f"Total keys migraterd: {len(self.keys)}")

    def get_src_keys(self):
        """ Populate the src keys from a thread. """
        timer = pytool.time.Timer()
        self.log.info("Querying source keys.")
        self.src_keys = self.src.keys(self.prefix)
        self.log.info(f"Retrieve source keys: {timer.elapsed}")
        self.log.info(f"Found {len(self.src_keys):,} source keys.")

    def get_dest_keys(self):
        """ Populate the destination keys from a thread. """
        timer = pytool.time.Timer()
        self.log.info("Querying destination keys.")
        self.dest_keys = self.dest.keys(self.prefix)
        self.log.info(f"Retrieve destination keys: {timer.elapsed}")
        self.log.info(f"Found {len(self.dest_keys):,} destination keys.")

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
        conn = parse_url(self.dest_url)
        client = get_client(conn)
        self._dest = client
        return self._dest


class DeleteWorker(threading.Thread):
    def __init__(self, key_queue, dest, log):
        self.queue = key_queue
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
                self.delete_key(key)
                metrics.count()
            except Exception as err:
                self.log.error(f"Error for key '{key}'")
                self.log.debug(err, exc_info=True)
                metrics.error()

        self.log.info(f"Thread completed. {count} keys processed.")

    def delete_key(self, key):
        """ Delete the key from the destination. """
        self.dest.delete(key)


class Delete:
    _dest = None

    def __init__(self, prefix, destination, workers=10):
        self.prefix = prefix
        self.dest_url = destination
        self.queue = queue.Queue()
        self.workers = workers
        self.log = Logger()

    def run(self):
        if not self.prefix or self.prefix == '*':
            self.log.error("Cowardly refusing to delete everything.")
            sys.exit(1)

        timer = pytool.time.Timer()

        # Get all our keys
        keys = self.dest.keys(self.prefix)

        self.debug.info(f"Time to retrieve keys: {timer.mark()}")

        total = len(keys)

        self.log.info(f"Running DELETE against '{self.prefix}' "
                      f"{self.dest_url}")
        self.log.info(f"There are {total:,} keys to delete.")
        sample = '\n  '.join(str(k) for k in keys[:10])
        self.log.info(f"Sample keys:\n  {sample}")
        self.log.info("Kill this process now if you don't want to proceed.\n"
                      "   ... Sleeping for 10 seconds while you decide.")

        time.sleep(10)

        timer.mark()
        self.log.info("Populating queue.")

        # Delete all the keys one by one...
        for key in keys:
            self.queue.put(key)

        self.log.debug(f"Time to populate queue: {timer.mark()}")
        self.log.debug(f"Keys in queue: {self.queue.qsize():,}")

        # Create metrics
        self.metrics = Metrics(self.prefix, len(self.keys))

        # Create worker threadpool
        timer.mark()
        self.log.debug(f"Creating {self.workers} workers.")
        self.pool = [DeleteWorker(self.queue, self.dest, self.log)
                     for i in range(self.workers)]
        self.log.debug(f"Time to create workers: {timer.mark()}")

        # Start all the worker threads
        self.log.info("Starting workers.")
        for worker in self.pool:
            worker.start()

        self.log.info(f"Startup time: {timer.elapsed}")

        # Wait for workers to finish
        self.log.info("Processing.")
        for worker in self.pool:
            worker.join()

        self.log.info(f"Copy time: {timer.mark()}")
        self.log.info(f"Total time taken: {timer.elapsed}")
        self.log.info(f"Total keys deleted: {len(self.keys)}")

        self.log.info("Finished.")

    @property
    def dest(self):
        """ Return a cached client connection object. """
        if self._dest:
            return self._dest

        # Parse and create a new client
        conn = parse_url(self.dest_url)
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
        self.opt('--workers', '-w', type=int, default=10,
                 help="Number of workers")
        self.opt('--logging', '-l', default='info',
                 choices=['debug', 'info', 'error'],
                 help="Set log level")
        self.opt('--overwrite', action='store_true',
                 help="Overwrite keys instead of skipping existing")
        self.opt('--delete-dest', action='store_true',
                 help="Do not migrate, delete destination keys")
        self.opt('--logfile', '-f', type=str, help="Log to file")
        self.opt('--prefix', '-p', default="*", help="source key prefix ")

    def run(self):
        self.log = Logger(getattr(logging, self.args.logging.upper()),
                          self.args.logfile)
        self.log.debug("Logging configured successfully.")

        self.log.info(f"Using prefix: {self.args.prefix}")

        if self.args.delete_dest:
            deleter = Delete(self.args.prefix, self.args.destination,
                             self.args.workers)
            deleter.run()
            return

        migrate = Migrate(self.args.prefix, self.args.source,
                          self.args.destination, self.args.workers,
                          self.args.overwrite)
        self.log.debug(f"Created migration runner.\n"
                       f"prefix = {self.args.prefix}\n"
                       f"workers = {self.args.workers}\n"
                       f"overwrite = {self.args.overwrite}")
        migrate.run()


if __name__ == '__main__':
    Main().start(sys.argv[1:])
