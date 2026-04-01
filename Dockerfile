FROM python:3.11-slim

WORKDIR /app

# Instalar dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

# Criar usuário não-root e ajustar permissões de /app (e /app/data, se necessário)
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appgroup /app

# Expor a porta que o FastAPI vai rodar
EXPOSE 8000

# Trocar para o usuário não-root antes de executar a aplicação
USER appuser

# Executar a aplicação
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--log-level", "info", \
     "--access-log"]