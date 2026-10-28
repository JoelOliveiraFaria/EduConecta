"""Utilitário: envio assíncrono do email de credenciais de primeiro acesso.

Usado só por /admin/utilizadores — quando um admin cria uma conta, o
utilizador recebe aqui a password temporária por email.
"""

import os
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import aiosmtplib


def smtp_configurado():
    """True se as credenciais SMTP (em .env.smtp) estiverem definidas."""
    return bool(os.environ.get("SMTP_USERNAME")) and bool(os.environ.get("SMTP_PASSWORD"))


async def enviar_credenciais(nome, email, password_temporaria):
    """Envia a password temporária por email via Gmail SMTP (SSL, porta 465).

    Levanta aiosmtplib.SMTPException se o destinatário for recusado pelo
    servidor — o controller apanha isto e mantém a conta bloqueada para
    revisão manual, em vez de a assumir como ativa sem confirmação de envio.
    """
    remetente = os.environ["SMTP_USERNAME"]
    password_smtp = os.environ["SMTP_PASSWORD"]

    mensagem = EmailMessage()
    mensagem["From"] = remetente
    mensagem["To"] = email
    mensagem["Subject"] = "EduConecta - Credenciais de primeiro acesso"
    mensagem["Date"] = formatdate(localtime=False)
    mensagem["Message-ID"] = make_msgid()

    mensagem.set_content(
        f"Olá, {nome}!\n\n"
        "Foi criada uma conta para ti na EduConecta.\n\n"
        f"Email de acesso: {email}\n"
        f"Palavra-passe temporária: {password_temporaria}\n\n"
        "No primeiro acesso, terás de definir uma nova palavra-passe "
        "antes de utilizar as funcionalidades da aplicação.\n\n"
        "Não partilhes estas credenciais.\n"
        "Se não reconheces esta conta, contacta a administração.\n\n"
        "Equipa EduConecta\n"
    )

    erros_smtp, _ = await aiosmtplib.send(
        mensagem,
        hostname="smtp.gmail.com",
        port=465,
        use_tls=True,
        username=remetente,
        password=password_smtp,
        timeout=15,
    )

    if erros_smtp:
        raise aiosmtplib.SMTPException("O destinatário foi recusado.")
