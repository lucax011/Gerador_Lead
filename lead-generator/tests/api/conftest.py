"""Fixtures compartilhadas para os testes da API.

TestClient com RabbitMQ mockado para evitar dependência de infraestrutura real.
Cobre apenas endpoints que não acessam banco de dados diretamente.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(scope="module")
def api_client():
    """TestClient com lifespan executado e RabbitMQ mockado.

    Escopo de módulo: uma única instância por arquivo de teste.
    Serve para endpoints puramente em memória (sweep state) e
    validações de input que falham antes de tocar o banco.
    """
    from fastapi.testclient import TestClient

    mock_pub = MagicMock()
    mock_pub.connect = AsyncMock()
    mock_pub.close = AsyncMock()
    mock_pub.publish = AsyncMock()

    with patch("services.api.main.RabbitMQPublisher", return_value=mock_pub):
        import services.api.main as mod

        with TestClient(mod.app, raise_server_exceptions=False) as tc:
            yield tc


@pytest.fixture(autouse=True)
def clear_sweep_state():
    """Limpa sweep_jobs antes e depois de cada teste para evitar vazamento de estado."""
    import services.api.main as mod

    mod.sweep_jobs.clear()
    yield
    mod.sweep_jobs.clear()
