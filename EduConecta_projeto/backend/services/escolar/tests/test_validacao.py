"""Testes: validadores partilhados em utils/validacao.py — morada e datas
(data_nascimento, data_admissao), acrescentados para enriquecer aluno,
encarregado, profissional e turma."""

from datetime import date

from utils.validacao import validar_data_iso, validar_data_nascimento, validar_morada


def test_validar_morada_vazia_e_valida():
    assert validar_morada("") is True


def test_validar_morada_dentro_do_limite():
    assert validar_morada("Rua Principal, 123") is True


def test_validar_morada_demasiado_longa():
    assert validar_morada("a" * 201) is False


def test_validar_morada_nao_texto():
    assert validar_morada(123) is False


def test_validar_data_iso_valida():
    assert validar_data_iso("2026-03-05") == date(2026, 3, 5)


def test_validar_data_iso_formato_errado():
    assert validar_data_iso("05/03/2026") is None


def test_validar_data_iso_nao_texto():
    assert validar_data_iso(20260305) is None


def test_validar_data_nascimento_valida():
    assert validar_data_nascimento("2020-01-01", hoje=date(2026, 1, 1)) is True


def test_validar_data_nascimento_no_futuro_e_invalida():
    assert validar_data_nascimento("2027-01-01", hoje=date(2026, 1, 1)) is False


def test_validar_data_nascimento_antes_de_1900_e_invalida():
    assert validar_data_nascimento("1899-12-31", hoje=date(2026, 1, 1)) is False


def test_validar_data_nascimento_formato_invalido():
    assert validar_data_nascimento("não é uma data") is False
