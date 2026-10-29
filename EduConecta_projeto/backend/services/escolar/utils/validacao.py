"""Utilitário: validações superficiais de campos partilhados entre
encarregados de educação e profissionais (cc, telemóvel, email).

Propositadamente simples — não há aqui verificação do dígito de controlo
do cartão de cidadão nem validação completa de formato de telemóvel/email;
isso exigiria lógica (ou uma dependência) que este serviço não tem. A
validação a sério do email é feita pelo serviço auth quando a conta é
criada (ver utils/auth_client.criar_conta_utilizador) — este módulo só
filtra entradas obviamente erradas antes de gastar um pedido de rede.
"""


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
