"""Shared fixtures for all test modules."""
import os
import sys

# Garante que o root do projeto está no path para imports sem instalar pacote
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Desliga cache do lru_cache do settings para testes não vazarem estado
from unittest.mock import patch
import pytest

from uuid import uuid4
from shared.models.lead import Lead


def make_lead(**kwargs) -> Lead:
    """Helper para criar Lead de teste com defaults sensatos."""
    defaults = dict(
        name="João Silva",
        email="joao@empresa.com.br",
        phone="+5511999990000",
        company="Tech Ltda",
        source_id=uuid4(),
        source_name="google_maps",
    )
    defaults.update(kwargs)
    return Lead(**defaults)
