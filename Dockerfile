FROM python:3.7

WORKDIR /usr/src/app

COPY requirements.txt requirements.txt

RUN pip install -r requirements.txt --compile

COPY . .

RUN flake8 .

ENTRYPOINT ["python", "/usr/src/app/main.py"]
