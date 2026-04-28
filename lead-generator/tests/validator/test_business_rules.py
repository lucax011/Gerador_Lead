"""Testes unitários das business rules do Validator.

Cobre validação de email, telefone, nome e a função
validate_lead() que combina todas as regras.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from services.validator.rules.business_rules import (
    validate_email,
    validate_phone,
    validate_name,
    validate_lead,
    DISPOSABLE_DOMAINS,
)


# ---------------------------------------------------------------------------
# validate_email
# ---------------------------------------------------------------------------

class TestValidateEmail:
    def test_email_corporativo_valido(self):
        assert validate_email("contato@empresa.com.br") == []

    def test_email_gmail_valido(self):
        assert validate_email("usuario@gmail.com") == []

    def test_email_subdominio_valido(self):
        assert validate_email("dev@mail.startup.io") == []

    def test_email_vazio_retorna_erro(self):
        erros = validate_email("")
        assert len(erros) == 1
        assert "required" in erros[0].lower()

    def test_email_sem_arroba_invalido(self):
        erros = validate_email("semaobase.com")
        assert any("Invalid email" in e for e in erros)

    def test_email_sem_dominio_invalido(self):
        erros = validate_email("usuario@")
        assert len(erros) > 0

    def test_email_com_espaco_invalido(self):
        erros = validate_email("usuario @empresa.com")
        assert len(erros) > 0

    def test_dominio_descartavel_mailinator(self):
        erros = validate_email("x@mailinator.com")
        assert any("Disposable" in e for e in erros)

    def test_dominio_descartavel_tempmail(self):
        erros = validate_email("temp@tempmail.com")
        assert any("Disposable" in e for e in erros)

    def test_dominio_descartavel_yopmail(self):
        erros = validate_email("teste@yopmail.com")
        assert any("Disposable" in e for e in erros)

    def test_todos_dominios_descartaveis_bloqueados(self):
        for domain in DISPOSABLE_DOMAINS:
            erros = validate_email(f"x@{domain}")
            assert any("Disposable" in e for e in erros), f"Domínio {domain} não bloqueado"

    def test_email_com_mais_invalido(self):
        """'+' é permitido em localpart por RFC."""
        assert validate_email("user+tag@empresa.com") == []

    def test_email_com_ponto_no_localpart(self):
        assert validate_email("nome.sobrenome@empresa.com.br") == []


# ---------------------------------------------------------------------------
# validate_phone
# ---------------------------------------------------------------------------

class TestValidatePhone:
    def test_telefone_none_valido(self):
        assert validate_phone(None) == []

    def test_telefone_brasileiro_com_ddi(self):
        assert validate_phone("+5511999990000") == []

    def test_telefone_sem_ddi(self):
        assert validate_phone("11999990000") == []

    def test_telefone_com_espacos(self):
        assert validate_phone("+55 11 99999-0000") == []

    def test_telefone_com_parenteses(self):
        assert validate_phone("(11) 99999-0000") == []

    def test_telefone_muito_curto(self):
        erros = validate_phone("123")
        assert len(erros) > 0

    def test_telefone_com_letras_invalido(self):
        erros = validate_phone("abc123efg")
        assert len(erros) > 0

    def test_telefone_espaco_branco_apenas(self):
        """String de espaços após strip retorna inválido por ser curto demais."""
        erros = validate_phone("   ")
        assert len(erros) > 0

    def test_telefone_muito_longo(self):
        erros = validate_phone("+" + "1" * 21)
        assert len(erros) > 0


# ---------------------------------------------------------------------------
# validate_name
# ---------------------------------------------------------------------------

class TestValidateName:
    def test_nome_valido(self):
        assert validate_name("João Silva") == []

    def test_nome_dois_caracteres(self):
        assert validate_name("Jo") == []

    def test_nome_vazio_retorna_erro(self):
        erros = validate_name("")
        assert len(erros) > 0

    def test_nome_apenas_espaco_retorna_erro(self):
        erros = validate_name("   ")
        assert len(erros) > 0

    def test_nome_um_caractere_invalido(self):
        erros = validate_name("J")
        assert any("2 characters" in e for e in erros)

    def test_nome_muito_longo_invalido(self):
        erros = validate_name("A" * 256)
        assert any("255" in e for e in erros)

    def test_nome_255_caracteres_valido(self):
        assert validate_name("A" * 255) == []

    def test_nome_none_retorna_erro(self):
        erros = validate_name(None)  # type: ignore
        assert len(erros) > 0


# ---------------------------------------------------------------------------
# validate_lead (integração das regras)
# ---------------------------------------------------------------------------

class TestValidateLead:
    def test_lead_valido_sem_erros(self):
        lead = {
            "name": "Maria Oliveira",
            "email": "maria@startup.com.br",
            "phone": "+5511988887777",
        }
        assert validate_lead(lead) == []

    def test_lead_sem_phone_valido(self):
        """Telefone é opcional."""
        lead = {"name": "Carlos", "email": "carlos@empresa.io"}
        assert validate_lead(lead) == []

    def test_lead_email_invalido_retorna_erro(self):
        lead = {"name": "Carlos", "email": "naoéemail", "phone": None}
        erros = validate_lead(lead)
        assert len(erros) > 0

    def test_lead_nome_vazio_retorna_erro(self):
        lead = {"name": "", "email": "ok@empresa.com", "phone": None}
        erros = validate_lead(lead)
        assert any("Name" in e for e in erros)

    def test_lead_multiplos_erros_acumulados(self):
        """Todos os erros devem aparecer, não apenas o primeiro."""
        lead = {"name": "", "email": "invalido", "phone": "abc"}
        erros = validate_lead(lead)
        assert len(erros) >= 2

    def test_lead_email_descartavel_retorna_erro(self):
        lead = {"name": "Fake User", "email": "x@guerrillamail.com", "phone": None}
        erros = validate_lead(lead)
        assert any("Disposable" in e for e in erros)

    def test_lead_sem_campos_retorna_erros_name_email(self):
        erros = validate_lead({})
        assert any("Name" in e for e in erros)
        assert any("Email" in e for e in erros or "required" in " ".join(erros).lower())
