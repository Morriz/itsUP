FROM python:3.11
WORKDIR /app
COPY requirements-prod.txt bin /app/
RUN .venv/bin/pip install -r requirements-prod.txt
COPY . /app
RUN .venv/bin/python -m unittest discover -s . -p '*_test.py'
CMD ["bin/start-api.sh"]
EXPOSE 8080