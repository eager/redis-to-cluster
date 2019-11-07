# redis-to-cluster

A poorly named repository for migrating Redis data between clusters. This
script has been tested migrating data from an ElastiCache Redis replica to an
ElastiCache Redis cluster.

This has been tested against Python *3.7*.

Features:

- Redis replica support
- Redis Cluster Mode support
- SSL (`rediss://`) support
- AUTH passwords
- Fast migrations with multithreading
- Partial migrations with key prefix filtering
- Missing TTL correction
- Metrics and time estimation

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
