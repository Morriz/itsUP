FROM python:3.11 as base
WORKDIR /app
COPY requirements-prod.txt /app/
RUN python -m venv .venv
RUN .venv/bin/pip install --no-cache-dir -r requirements-prod.txt

FROM base as ci
COPY . /app
RUN .venv/bin/pip install pylint

FROM ci as test
RUN .venv/bin/python -m unittest discover -s . -p '*_test.py'
RUN .venv/bin/pylint **/*.py

FROM python:3.11-alpine
WORKDIR /app
COPY --from=base /app /app
COPY . /app
CMD [".venv/bin/uvicorn", "api.main:app", "--port", "8080", "--host", "0.0.0.0"]
VOLUME /hostpipe