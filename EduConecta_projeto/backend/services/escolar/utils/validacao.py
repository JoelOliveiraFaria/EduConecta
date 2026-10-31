"""Utilitário: validações superficiais de campos partilhados entre
encarregados de educação, profissionais e alunos (cc, telemóvel, email,
morada, datas).

Propositadamente simples — não há aqui verificação do dígito de controlo
do cartão de cidadão nem validação completa de formato de telemóvel/email;
isso exigiria lógica (ou uma dependência) que este serviço não tem. A
validação a sério do email é feita pelo serviço auth quando a conta é
criada (ver utils/auth_client.criar_conta_utilizador) — este módulo só
filtra entradas obviamente erradas antes de gastar um pedido de rede.
"""

from datetime import date


def validar_cc(cc):
    """Número de cartão de cidadão: texto não vazio, até 30 caracteres."""
    return isinstance(cc, str) and 5 <= len(cc.strip()) <= 30


def validar_telemovel(telemovel):
    """Telemóvel é opcional — string vazia é válida; se vier preenchido, até 30 caracteres."""
    return isinstance(telemovel, str) and len(telemovel.strip()) <= 30


def validar_email_superficial(email):
    """Forma mínima de um email — o auth é quem valida a sério (RFC, domínio)."""
    return (
        isinstance(email, str)
        and 3 <= len(email.strip()) <= 254
        and "@" in email.strip()
    )


def validar_morada(morada):
    """Morada é opcional — string vazia é válida; se vier preenchida, até 200 caracteres."""
    return isinstance(morada, str) and len(morada.strip()) <= 200


def validar_data_iso(valor):
    """Valida uma data no formato AAAA-MM-DD; devolve o `date` correspondente,
    ou None se o valor não for uma data válida nesse formato."""
    if not isinstance(valor, str):
        return None
    try:
        return date.fromisoformat(valor.strip())
    except ValueError:
        return None


def validar_data_nascimento(valor, hoje=None):
    """Data de nascimento: formato AAAA-MM-DD, não pode ser no futuro nem
    anterior a 1900 (filtro de sanidade, não validação de idade mínima)."""
    data = validar_data_iso(valor)
    if data is None:
        return False
    hoje = hoje or date.today()
    return date(1900, 1, 1) <= data <= hoje
