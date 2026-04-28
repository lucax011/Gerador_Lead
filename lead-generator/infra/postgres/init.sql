-- Extensões necessárias para o banco de dados.
-- Todas as tabelas, índices e seeds são gerenciados exclusivamente pelo Alembic.
-- Para aplicar o schema: alembic upgrade head
CREATE SCHEMA IF NOT EXISTS public;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
