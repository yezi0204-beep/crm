FROM python:3.10-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app.py .
COPY crm_app.db .

RUN mkdir -p /app/uploads/contracts

EXPOSE 5000

CMD ["python", "-c", "import os; os.environ['FLASK_DEBUG'] = '0'; exec(open('app.py').read())"]