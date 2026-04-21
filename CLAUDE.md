# CLAUDE.md — Gerador de Leads

## Arquitetura
- Microservices + Event-Driven com RabbitMQ
- Cada serviço fica em services/<nome>/
- Modelos compartilhados em shared/models/
- Broker abstraction em shared/broker/

## Stack
- Python 3.11 | FastAPI | Pydantic v2
- PostgreSQL + SQLAlchemy + Alembic
- RabbitMQ (aio-pika para async)
- Docker / Docker Compose

## Convenções
- Eventos em snake_case: lead.captured, lead.scored
- Models Pydantic para todos os payloads
- Variáveis de ambiente via pydantic-settings (config.py)
- Cada worker tem seu próprio Dockerfile

## Comandos uteis
- docker compose up --build     # sobe tudo
- alembic upgrade head          # aplica migrations
- pytest services/<svc>/tests/  # roda testes do servico