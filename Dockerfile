FROM python:3.7

WORKDIR /usr/src/app

COPY . .

RUN pip install -r requirements.txt --compile

ENTRYPOINT ["python", "/usr/src/app/redis-to-cluster.py"]
