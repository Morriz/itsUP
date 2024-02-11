FROM python:3.11
WORKDIR /app
COPY requirements-prod.txt /app/
RUN pip install --no-cache-dir -r requirements-prod.txt
COPY . /app
RUN python -m unittest discover -s . -p '*_test.py'
CMD ["uvicorn", "api.main:app", "--port", "8080", "--host", "0.0.0.0"]
VOLUME /hostpipe