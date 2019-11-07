# redis-to-cluster

A poorly named repository for migrating Redis data between clusters. This
script has been tested migrating data from an ElastiCache Redis replica to an
ElastiCache Redis cluster.

This has been tested against Python *3.7*.

**Features**:

- Redis replica support
- Redis Cluster Mode support
- SSL (`rediss://`) support
- AUTH passwords
- Fast migrations with multithreading
- Partial migrations with key prefix filtering
- Missing TTL correction
- Metrics and time estimation

## Example output

This is a sanitized example of the output produced by this script, including
the command to run it, and an exception during copying.

```
ubuntu@redis-util:~$ docker run -it --rm --name redis-util6 -v "$PWD/ttl.log:/usr/src/app/ttl.log" \
    shakefu/redis-to-cluster --workers 15 --prefix 'spring:*' --logging debug \
    --source redis://redis-example.cache.amazonaws.com:6379/0 \
    --destination rediss://:password@redis-cluster-example.cache.amazonaws.com:6379/
2019-11-06 22:24:02,274 [DEBUG] Logging configured successfully.
2019-11-06 22:24:02,274 [INFO] Using prefix: spring:*
2019-11-06 22:24:02,274 [DEBUG] Created migration runner.
prefix = spring:*
workers = 15
overwrite = False
2019-11-06 22:24:02,274 [INFO] Starting migration.
2019-11-06 22:24:02,274 [INFO] Querying source keys.
2019-11-06 22:24:02,274 [INFO] No password set for redis-example.cache.amazonaws.com
2019-11-06 22:24:02,275 [INFO] Querying destination keys.
2019-11-06 22:24:02,275 [INFO] Using cluster mode for redis-cluster-example.cache.amazonaws.com
2019-11-06 22:26:02,507 [INFO] Retrieve source keys: 0:02:00.232611
2019-11-06 22:26:02,507 [INFO] Found 29,157,514 source keys.
2019-11-06 22:29:30,343 [INFO] Retrieve destination keys: 0:05:28.067949
2019-11-06 22:29:30,343 [INFO] Found 28,567,223 destination keys.
2019-11-06 22:29:30,343 [INFO] Time to retrieve keys: 0:05:28.069108
2019-11-06 22:29:52,413 [DEBUG] Time to compute set: 0:00:22.070054
2019-11-06 22:29:52,413 [INFO] Keys to process: 592,530
2019-11-06 22:29:52,413 [INFO] Populating queue.
2019-11-06 22:29:53,459 [DEBUG] Time to populate queue: 0:00:01.045916
2019-11-06 22:29:53,459 [DEBUG] Keys in queue: 592,530
2019-11-06 22:29:53,459 [DEBUG] Creating 15 workers.
2019-11-06 22:29:53,459 [DEBUG] Time to create workers: 0:00:00.000158
2019-11-06 22:29:53,459 [INFO] Starting workers.
2019-11-06 22:29:55,403 [INFO] Startup time: 0:05:53.129592
2019-11-06 22:29:55,404 [INFO] Processing.
2019-11-06 22:29:59,922 [INFO] spring:*: 0.259ms avg, 0.1min passed, 2.4min remaining. (25,000/592,530)
2019-11-06 22:30:04,456 [INFO] spring:*: 0.22ms avg, 0.2min passed, 2.0min remaining. (50,000/592,530)
2019-11-06 22:30:08,974 [INFO] spring:*: 0.207ms avg, 0.3min passed, 1.8min remaining. (75,000/592,530)
2019-11-06 22:30:13,434 [INFO] spring:*: 0.2ms avg, 0.3min passed, 1.6min remaining. (100,000/592,530)
2019-11-06 22:30:17,947 [INFO] spring:*: 0.196ms avg, 0.4min passed, 1.5min remaining. (125,000/592,530)
2019-11-06 22:30:22,475 [INFO] spring:*: 0.193ms avg, 0.5min passed, 1.4min remaining. (150,000/592,530)
2019-11-06 22:30:30,159 [INFO] spring:*: 0.21ms avg, 0.6min passed, 1.5min remaining. (175,000/592,530)
2019-11-06 22:30:34,644 [INFO] spring:*: 0.206ms avg, 0.7min passed, 1.3min remaining. (200,000/592,530)
2019-11-06 22:30:39,124 [INFO] spring:*: 0.203ms avg, 0.8min passed, 1.2min remaining. (225,000/592,530)
2019-11-06 22:30:43,677 [INFO] spring:*: 0.201ms avg, 0.8min passed, 1.1min remaining. (250,000/592,530)
2019-11-06 22:30:48,156 [INFO] spring:*: 0.199ms avg, 0.9min passed, 1.1min remaining. (275,000/592,530)
2019-11-06 22:30:52,635 [INFO] spring:*: 0.197ms avg, 1.0min passed, 1.0min remaining. (300,000/592,530)
2019-11-06 22:30:57,196 [INFO] spring:*: 0.196ms avg, 1.1min passed, 0.9min remaining. (325,000/592,530)
2019-11-06 22:31:01,669 [INFO] spring:*: 0.195ms avg, 1.1min passed, 0.8min remaining. (350,000/592,530)
2019-11-06 22:31:01,704 [ERROR] Error for key 'b'spring:session:expires:333f9f43-4b06-4252-8d7e-080c0aaaaaa''
2019-11-06 22:31:01,705 [DEBUG] DUMP payload version or checksum are wrong
Traceback (most recent call last):
  File "/usr/src/app/main.py", line 181, in run
    self.copy_key(key)
  File "/usr/src/app/main.py", line 213, in copy_key
    self.dest.restore(key, ttl, value, replace=True)
  File "/usr/local/lib/python3.7/site-packages/redis/client.py", line 1138, in restore
    return self.execute_command('RESTORE', *params)
  File "/usr/local/lib/python3.7/site-packages/rediscluster/utils.py", line 101, in inner
    return func(*args, **kwargs)
  File "/usr/local/lib/python3.7/site-packages/rediscluster/client.py", line 371, in execute_command
    return self.parse_response(r, command, **kwargs)
  File "/usr/local/lib/python3.7/site-packages/redis/client.py", line 680, in parse_response
    response = connection.read_response()
  File "/usr/local/lib/python3.7/site-packages/redis/connection.py", line 629, in read_response
    raise response
redis.exceptions.ResponseError: DUMP payload version or checksum are wrong
2019-11-06 22:31:06,117 [INFO] spring:*: 0.194ms avg, 1.2min passed, 0.7min remaining. (375,001/592,530)
2019-11-06 22:31:10,548 [INFO] spring:*: 0.193ms avg, 1.3min passed, 0.6min remaining. (400,001/592,530)
2019-11-06 22:31:15,351 [INFO] spring:*: 0.193ms avg, 1.4min passed, 0.5min remaining. (425,001/592,530)
2019-11-06 22:31:19,819 [INFO] spring:*: 0.192ms avg, 1.4min passed, 0.5min remaining. (450,001/592,530)
2019-11-06 22:31:24,324 [INFO] spring:*: 0.191ms avg, 1.5min passed, 0.4min remaining. (475,001/592,530)
2019-11-06 22:31:28,773 [INFO] spring:*: 0.191ms avg, 1.6min passed, 0.3min remaining. (500,001/592,530)
2019-11-06 22:31:33,280 [INFO] spring:*: 0.19ms avg, 1.7min passed, 0.2min remaining. (525,001/592,530)
2019-11-06 22:31:37,699 [INFO] spring:*: 0.19ms avg, 1.7min passed, 0.1min remaining. (550,001/592,530)
2019-11-06 22:31:42,238 [INFO] spring:*: 0.189ms avg, 1.8min passed, 0.1min remaining. (575,001/592,530)
2019-11-06 22:31:45,353 [INFO] Thread completed. 39499 keys processed.
2019-11-06 22:31:45,353 [INFO] Thread completed. 39530 keys processed.
2019-11-06 22:31:45,354 [INFO] Thread completed. 39678 keys processed.
2019-11-06 22:31:45,354 [INFO] Thread completed. 39157 keys processed.
2019-11-06 22:31:45,354 [INFO] Thread completed. 39488 keys processed.
2019-11-06 22:31:45,354 [INFO] Thread completed. 39495 keys processed.
2019-11-06 22:31:45,354 [INFO] Thread completed. 39543 keys processed.
2019-11-06 22:31:45,354 [INFO] Thread completed. 39516 keys processed.
2019-11-06 22:31:45,354 [INFO] Thread completed. 39546 keys processed.
2019-11-06 22:31:45,354 [INFO] Thread completed. 39543 keys processed.
2019-11-06 22:31:45,355 [INFO] Thread completed. 39478 keys processed.
2019-11-06 22:31:45,355 [INFO] Thread completed. 39475 keys processed.
2019-11-06 22:31:45,355 [INFO] Thread completed. 39653 keys processed.
2019-11-06 22:31:45,355 [INFO] Thread completed. 39553 keys processed.
2019-11-06 22:31:45,355 [INFO] Thread completed. 39376 keys processed.
2019-11-06 22:31:45,356 [INFO] Copy time: 0:01:51.896510
2019-11-06 22:31:45,356 [INFO] Total time taken: 0:07:43.082167
2019-11-06 22:31:45,356 [INFO] Total keys migraterd: 592530
```

## Installation

This section describes how to install the redis-to-cluster script.

### Docker

The preferred way to use this utility is with a Docker image. You can get the
image by running *docker pull*.

```bash
# Get the image from Docker Hub
$ docker pull shakefu/redis-to-cluster:latest
```

### Python

There is no PyPI package for this script, since it's intended primarily to be
used via Docker containers. If, however, you desire to use it natively, you can
do so.

It's highly recommended you use a virtualenv to prevent dependency issues

```bash
# CLone the repository
$ git clone https://github.com/shakefu/redis-to-cluster.git
# Make a virtualenv and activate it using virtualenvwrapper
$ mkvirtualenv redis-to-cluster
# Install Python dependencies
$ pip install -r requirements.txt
# Run the script
$ python main.py --help
```

## Usage

This section describes how to use the redis-to-cluster script and its
behaviors.

The script operates in three phases when migrating. First, it queries both the
*source* Redis and *destination* Redis to find all keys matching the provided
*prefix* (default `*`). Second, it computes all the keys which are in the
source, but not in the destination. Third, it copies those keys over.

With each key copied, the TTL of the key in the source is checked. If the TTL
returns -2, the key is ignored. If the TTL returns -1 (no expiration), it will
be set to 90 days when copied. Any other TTL value is copied along with the key
and its value.

Keys without a TTL expiration set will also be written out to `./ttl.log` for
auditing purposes, which by default is present inside the container. If you
wish to extract this file, either do so after the container has run, before
removal, or create and volume mount a file to be written to into the container.
Inside the container this log file will be located at `/usr/src/app/ttl.log`.

### Quick examples

To simply copy all keys with default arguments:

```bash
docker run shakefu/redis-to-cluster --source redis://redis.example:6739/0 \
    --destination redis://redis-new.example:6739/0
```

To copy all keys matching `spring:*` from an open authentication Redis replica,
to an authenticated Redis cluster, on ElastiCache, while extracting the log of
keys with no TTL, using 15 thread workers, with debug level output.

```bash
docker run -it --rm --name redis-util1 -v "$PWD/ttl.log:/usr/src/app/ttl.log" \
    shakefu/redis-to-cluster --workers 15 --prefix 'spring:*' --logging debug \
    --source redis://redis-example.cache.amazonaws.com:6379/0 \
    --destination rediss://:PASSWORD@redis-cluster-example.cache.amazonaws.com:6379/
```

To delete all keys matching `spring:*` from the destination Redis ElastiCache
cluster using 15 worker threads, with debug level logging. The *source*
argument is required but not used for this operation.

```bash
docker run -it --rm --name redis-del1 shakefu/redis-to-cluster --delete-dest \
    --workers 15 --prefix 'spring:*' --logging debug --source redis://unused/0 \
    --destination rediss://:PASSWORD@redis-cluster-example.cache.amazonaws.com:6379/
```

*TODO: More useful examples.*

### Redis URLs

The provided *source* and *destination* Redis URLs must strictly conform to the
Redis URI scheme. [\[1\]](http://www.iana.org/assignments/uri-schemes/prov/redis)

The general format is `schema://(:password)@host:port/db`. The *schema* must be
either `redis` or `rediss` for SSL. The *password* must be prefixed with a `:`
if present. If you are connecting to a cluster, the *db* number may be omitted,
but the trailing slash on the URL must be present.

**Examples**:

```bash
# Open authentication Redis replica
redis://redis.example:6739/0
# SSL Redis replica
rediss://redis.example:443/0
# Open authentication Redis cluster
redis://redis-cluster.example:6739/
# Authenticated+SSL Redis cluster
rediss://:password@redis-cluster.example:6739/
```

### Arguments

This section contains argument descriptions and their behaviors and values.

#### `--source` `-s` (required)

The source Redis URL to connect to. Keys will be read from this Redis. See the
section on Redis URLs for more specifics. If you are using `--delete-dest`,
this may be a bogus URL as long as it validates, such as `redis://unused/0`.

#### `--destination` `-d` (required)

The destination Redis URL to connect to. Keys will be written to this Redis, or
deleted from this Redis if you are using `--delete-dest`. See the section on
Redis URLs for more specifics.

#### `--prefix` `-p` (default: `*`)

The key prefix to match when copying keys between Redis hosts, or to delete
when using `--delete-dest`. If you are using `--delete-dest` this may **not**
be left as the default.

#### `--overwrite`

If this option is set, it will change the behavior of the script to always copy
all keys matching *prefix*, regardless if they are already present in the
*destination*.

#### `--delete-dest`

If this option is set, intstead of copying from the *source* to the
*destination*, the script will delete keys matching *prefix* from the
destination URL. If this is set, the prefix must not be equal to `*`, the
wildcard matching all keys.

When the script runs with this option, it will first query destination keys,
provide a sample output of keys, and wait 10 seconds before executing to allow
time for you to kill the program (`ctrl-c`) before the destructive process
begins.

Deletion is generally faster than copying, so you may use more worker threads
if desired.

#### `--workers` `-w` (default: `10`)

The number of worker threads to use when copying keys between Redis hosts. This
value should be tuned based on the size of your Redis hosts and the host CPU
running the script. The default value should be enough to provide a reasonable
amount of load, but this value will be highly variable.

If you are maxing out your throughput for a single process, you may run
multiple instances in parallel using non-overlapping `--prefix` values. Keep a
close eye on your Redis or cluster if you are doing this since it may be
overwhelmed.

#### `--logging` `-l` (default: `info`)

*Must be one of*: debug, info, error

Set the logging level for the script. The logging level name provided must be
lower case. Error will only show errors. Info will provide additional helpful
output and timing metrics. Debug will add further output and tracebacks to
errors.

#### `--logfile` `-f` (default: `stdout`)

Filename to write output to. If this is not set, output will be written to
stdout.

#### `--help`

This will display the command line help and exit.

```
$ docker run shakefu/redis-to-cluster --help
usage: main.py --source SOURCE --destination DESTINATION [--workers WORKERS]
               [--logging {debug,info,error}] [--overwrite] [--delete-dest]
               [--logfile LOGFILE] [--prefix PREFIX] [--help]

Simple script to migrate Redis database key data, in a non destructive way.

optional arguments:
  --source SOURCE, -s SOURCE            source Redis server / cluster
  --destination DESTINATION, -d DESTINATION
                                        destination Redis server / cluster
  --workers WORKERS, -w WORKERS         Number of workers
  --logging {debug,info,error}, -l {debug,info,error}
                                        Set log level
  --overwrite                           Overwrite keys instead of skipping
                                        existing
  --delete-dest                         Do not migrate, delete destination
                                        keys
  --logfile LOGFILE, -f LOGFILE         Log to file
  --prefix PREFIX, -p PREFIX            source key prefix
  --help                                display this help and exit
```

## Credits

Forked from
[u2mejc/redis-to-cluster](https://github.com/u2mejc/redis-to-cluster) which was
based on Github Gist
[josegonzalez/redis_migrate.py](https://gist.github.com/josegonzalez/6049a72cb163337a18102743061dfcac),
which is a fork of
[iserko/redis_migrate.py](https://gist.github.com/iserko/9258373).
