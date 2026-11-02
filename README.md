# EduConecta

Plataforma de comunicação entre instituições de ensino (creche, pré-escolar e ensino básico) e as famílias, desenvolvida com uma arquitetura de microserviços.

> Trabalho prático da unidade curricular **Arquiteturas e Integração de Sistemas**, Mestrado em Engenharia Informática, Escola Superior de Tecnologia do IPCA.

---

## Índice

- [Sobre o projeto](#sobre-o-projeto)
- [Estado do projeto](#estado-do-projeto)
- [Perfis de utilizador](#perfis-de-utilizador)
- [Arquitetura](#arquitetura)
- [Microserviços](#microserviços)
- [Eventos](#eventos)
- [Tecnologias](#tecnologias)
- [Executar localmente](#executar-localmente)
- [Testes](#testes)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Processos de negócio (BPMN)](#processos-de-negócio-bpmn)
- [Equipa](#equipa)

---

## Sobre o projeto

A comunicação entre a escola e os encarregados de educação está muitas vezes dispersa por papel, telefone, email e grupos de mensagens. Isso dificulta o acompanhamento das crianças e o registo de informação importante.

O **EduConecta** reúne essa comunicação numa única plataforma:

- **Faltas e justificações:** o docente regista as faltas, o encarregado de educação é notificado e pode submeter uma justificação com observações e anexo, e o docente ou educador aprova ou rejeita. O encarregado é notificado da decisão.
- **Acompanhamento diário:** na creche, os profissionais registam alimentação, sono, higiene, atividades e observações, e o encarregado consulta o registo do dia.
- **Comunicados e conversas:** docentes e educadores publicam comunicados para uma turma, com fotografias, e os encarregados conversam em privado com os profissionais do educando (mensagens com fotografia e vídeo).
- **Gestão escolar:** o administrador configura turmas, alunos, encarregados, profissionais e as respetivas associações, e cria as contas dos utilizadores.

## Estado do projeto

O back end está implementado e corre com Docker Compose. A infraestrutura de produção e o front end ainda não estão neste repositório.

| Área | Estado |
|---|---|
| Seis microserviços (Auth, Escolar, Assiduidade, Diário, Comunicados, Notificações) | Implementados, com testes e documentação OpenAPI |
| API Gateway | Implementado: ponto único de entrada, autenticação, limites de pedidos |
| Mensagens assíncronas (RabbitMQ) | Implementadas: 5 tipos de evento consumidos pelas Notificações |
| Base de dados por serviço (MongoDB Atlas) | Implementada |
| Front end (React) | Por fazer |
| Deploy na cloud (AWS, Kubernetes) | Por fazer |
| Aviso periódico do prazo de justificação | Por fazer (hoje só há aviso quando a falta é registada) |
| Confirmação de leitura dos comunicados | Por fazer |

## Perfis de utilizador

| Perfil | Acesso |
|---|---|
| **Administrador** | Configuração da instituição: turmas, alunos, encarregados, profissionais, contas e perfis. |
| **Docente / Educador** | Registo de faltas, decisão sobre justificações, diário, comunicados e conversas com os encarregados. |
| **Auxiliar de ação educativa** | Acompanhamento diário das crianças. Não participa nas conversas privadas. |
| **Encarregado de educação** | Consulta de informação dos seus educandos, submissão de justificações, leitura de comunicados e conversas com os profissionais. |

## Arquitetura

![Arquitetura do EduConecta](Diagrama%20Arquitetura%20de%20Software/SVG/Arquitetura%20de%20Software.svg)

A solução segue o padrão de **microserviços**. O diagrama mostra a arquitetura alvo; esta tabela separa o que existe hoje do que está previsto.

| Aspeto | Hoje | Previsto |
|---|---|---|
| Execução | Docker Compose | Kubernetes (k3s em EC2), um container por microserviço |
| Entrada da API | API Gateway em Python, em `http://localhost:8081/api` | O mesmo, atrás do Amazon CloudFront, que encaminha `/api` para o cluster |
| Front end | Não existe | React servido pelo CloudFront a partir de um bucket S3 |
| Emails | SMTP, no serviço Auth (palavra-passe temporária) | Amazon SES |
| Credenciais | Ficheiros `.env` | Kubernetes Secrets |

O que é comum aos dois:

- **API Gateway:** ponto único de entrada da API, sob `/api`. Valida o token JWT, limita as tentativas de login e o tamanho dos pedidos, e encaminha cada pedido para o serviço responsável. Os serviços não publicam portas, por isso só se chegam a eles pelo gateway. O plano e as decisões estão em [`docs/api-gateway-plano.md`](EduConecta_projeto/docs/api-gateway-plano.md).
- **Comunicação síncrona:** APIs REST, documentadas com OpenAPI. Cada serviço valida a sessão chamando o `/me` do Auth.
- **Comunicação assíncrona:** eventos publicados no RabbitMQ e consumidos pelo serviço de Notificações.
- **Database per Service:** cada microserviço tem a sua própria base de dados lógica no MongoDB Atlas.

## Microserviços

| Serviço | Responsabilidade |
|---|---|
| **Gateway** | Ponto único de entrada: autenticação do token, limites, encaminhamento, estado dos serviços e documentação agregada |
| **Auth** | Contas, perfis, palavra-passe temporária enviada por email, autenticação e emissão de JWT |
| **Gestão Escolar** | Turmas (creche ou ensino básico, com ano letivo), alunos, encarregados, profissionais e as suas associações |
| **Assiduidade** | Marcação de faltas e justificações, com anexo, aprovação e rejeição |
| **Diário** | Registos diários da creche: alimentação, sono, higiene, atividades e observações |
| **Comunicados** | Comunicados por turma, com fotografias, e conversas privadas entre encarregados e profissionais |
| **Notificações** | Consumo de eventos e notificações na plataforma para cada utilizador |

Cada serviço publica a sua documentação em `http://localhost:8081/api/docs`.

## Eventos

Os serviços publicam no exchange `educonecta.eventos` (tipo topic) do RabbitMQ. A publicação é "melhor esforço": se o RabbitMQ estiver indisponível o pedido não falha, mas o aviso perde-se.

| Evento (routing key) | Publicado por | O que as Notificações fazem |
|---|---|---|
| `falta.registada` | Assiduidade | Avisam os encarregados do aluno de que há uma falta por justificar |
| `falta.justificacao.submetida` | Assiduidade | Avisam os profissionais da turma de que há uma justificação por decidir |
| `falta.justificacao.decidida` | Assiduidade | Avisam o encarregado de que a justificação foi aprovada ou rejeitada |
| `comunicado.criado` | Comunicados | Avisam os encarregados dos alunos da turma |
| `aluno.eliminado` | Gestão Escolar | Só regista uma entrada de auditoria |

## Tecnologias

| Área | Tecnologia |
|---|---|
| Back end | Python: Flask (Escolar, Assiduidade, Diário, Comunicados, Notificações) e Quart (Auth, Gateway) |
| API Gateway | Quart, httpx e PyJWT |
| Base de dados | MongoDB Atlas (PyMongo) |
| Mensagens assíncronas | RabbitMQ (pika) |
| Autenticação | JWT (HS256, validade de 15 minutos) |
| Containers | Docker e Docker Compose |
| Documentação da API | OpenAPI (Swagger UI) |
| Testes | pytest, scripts de integração e coleção Postman |
| Front end (previsto) | React |
| Cloud (prevista) | AWS: EC2, S3, CloudFront, SES, ECR, CloudWatch, com Kubernetes (k3s) |

## Executar localmente

Guia passo a passo para correr o back end completo num PC novo (Windows, macOS ou Linux).

### 1. Pré-requisitos

| Ferramenta | Para quê | Como verificar |
|---|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) (inclui o Docker Compose) | Corre todos os serviços | `docker --version` e `docker compose version` |
| [Git](https://git-scm.com/downloads) | Obter o código | `git --version` |
| Credenciais do MongoDB Atlas da equipa | Base de dados (cada serviço usa a sua) | Pedir à equipa |

Abra o Docker Desktop e espere que fique "running" antes de continuar. Os portos `8081`, `5672` e `15672` têm de estar livres.

### 2. Obter o código

```bash
git clone https://github.com/JoelOliveiraFaria/EduConecta.git
cd EduConecta
git checkout MVC
cd EduConecta_projeto
```

Todos os comandos seguintes correm dentro de `EduConecta_projeto`.

### 3. Ligar à base de dados (MongoDB Atlas)

O projeto usa o cluster Atlas da equipa. **Não é preciso criar nenhum cluster**, mas é preciso ter as credenciais e autorizar o IP.

1. **Credenciais:** a equipa envia ao docente, em privado (email ou mensagem, nunca no repositório), o ficheiro `.env` já preenchido ou a `MONGO_URI` com o utilizador e a palavra-passe.
2. **Autorizar o IP:** o Atlas só aceita ligações de IPs autorizados. O docente vê o seu IP público em [whatismyip.com](https://www.whatismyip.com) e envia-o à equipa, que o adiciona em *Network Access > Add IP Address* no Atlas. Se mudar de rede, o IP muda e tem de ser adicionado de novo.

As bases e coleções já existem no cluster; os serviços criam as que faltarem ao arrancar.

> Algumas redes (como a eduroam) bloqueiam a porta 27017 do Atlas. Se os serviços não chegarem à base de dados, experimente outra rede ou o hotspot do telemóvel.

<details>
<summary>Para a equipa: criar o acesso do docente no Atlas</summary>

1. *Database Access > Add New Database User*: crie um utilizador para o docente, com palavra-passe forte e o papel *Read and write to any database* (ou apenas às bases listadas no `.env.example`).
2. *Network Access > Add IP Address*: adicione o IP do docente. `0.0.0.0/0` aceita qualquer IP e só deve ser usado temporariamente, para a avaliação.
3. Em *Connect > Drivers*, copie a connection string, substitua `<password>` e envie-a em privado.
4. Depois da avaliação, apague o utilizador e o IP.

</details>

### 4. Criar os ficheiros de configuração

**`.env`** (obrigatório). Se a equipa já enviou o `.env` preenchido, copie-o para esta pasta e salte esta parte. Caso contrário, copie o modelo e preencha-o:

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
```

| Variável | O que pôr |
|---|---|
| `MONGO_URI` | A connection string enviada pela equipa (passo 3) |
| `MONGO_*_DATABASE` | Pode deixar os nomes por omissão |
| `RABBITMQ_USER`, `RABBITMQ_PASS` | Qualquer utilizador e palavra-passe (servem para o painel do RabbitMQ) |
| `JWT_SECRET_KEY` | Texto aleatório com **pelo menos 32 caracteres** |
| `INTERNAL_SERVICE_KEY` | Outro texto aleatório |

Pode gerar um segredo com `openssl rand -hex 32` ou `python -c "import secrets; print(secrets.token_hex(32))"`.

**`.env.smtp`** (obrigatório existir, mas pode ter valores vazios). O Auth usa-o para enviar a palavra-passe temporária por email:

```
SMTP_USERNAME=
SMTP_PASSWORD=
```

Sem credenciais SMTP reais o sistema funciona, mas não envia emails.

### 5. Arrancar

```bash
docker compose up -d --build
```

A primeira vez demora alguns minutos (construção das imagens). Depois confirme:

```bash
docker compose ps
```

Todos os contentores devem aparecer como `healthy` (ou `running`).

### 6. Verificar que funciona

| O quê | Onde |
|---|---|
| API (através do gateway) | `http://localhost:8081/api` |
| Documentação de cada serviço | `http://localhost:8081/api/docs` |
| Estado de todos os serviços | `http://localhost:8081/api/ready` (deve devolver `"status": "ready"`) |
| Painel do RabbitMQ | `http://localhost:15672` (utilizador e palavra-passe do `.env`) |

Se `/api/ready` indicar `not_ready`, falta um serviço ou a ligação ao Atlas. `docker compose ps` e `docker compose logs <serviço>` mostram o motivo.

### 7. Experimentar a API

O caminho mais rápido é a coleção do Postman, que tem um pedido para cada rota. Siga o [README da pasta](EduConecta_projeto/postman/README.md): importar os dois ficheiros, escolher o ambiente `EduConecta - Local` e fazer login. O login precisa de uma conta existente; as contas são criadas por um administrador.

### Comandos úteis

```bash
docker compose logs -f gateway     # ver os logs de um serviço
docker compose restart auth        # reiniciar um serviço
docker compose down                # parar tudo
docker compose down -v             # parar e apagar volumes
```

Para falar diretamente com um serviço (depuração), reabra as portas `5001` a `5006`:

```bash
docker compose -f compose.yaml -f compose.debug.yaml up -d
```

### Problemas comuns

| Sintoma | Causa provável |
|---|---|
| `Falta MONGO_URI no .env` (ou outra variável) | O `.env` não existe ou está incompleto |
| `env file .env.smtp not found` | Falta criar o `.env.smtp` (passo 4) |
| `cannot connect to the Docker daemon` | O Docker Desktop não está aberto |
| `port is already allocated` | Outro programa usa o porto 8081, 5672 ou 15672 |
| Serviços reiniciam sem parar | Atlas inacessível: IP não autorizado, credenciais erradas ou rede a bloquear a porta 27017 |
| `/api/ready` devolve `not_ready` | Algum serviço ainda está a arrancar ou falhou; veja `docker compose ps` |

## Testes

Cada serviço e o gateway têm testes `pytest`, que não precisam de rede nem do Atlas. Dentro da pasta do serviço (por exemplo `EduConecta_projeto/backend/services/escolar` ou `EduConecta_projeto/backend/gateway`):

```bash
pip install -r requirements-dev.txt
pytest
```

A coleção do Postman em [`EduConecta_projeto/postman`](EduConecta_projeto/postman) tem um pedido para cada rota da API, com variáveis e testes. O [README da pasta](EduConecta_projeto/postman/README.md) explica como a usar.

Os scripts de integração em [`EduConecta_projeto/testes_manuais`](EduConecta_projeto/testes_manuais) correm contra o sistema a funcionar e pedem as credenciais no terminal. Os que usam `127.0.0.1:8081` passam pelo gateway. Os que usam `http://auth:8000` e semelhantes correm dentro dos contentores, na rede interna.

## Estrutura do repositório

```
EduConecta/
├── Diagrama Arquitetura de Software/    Diagrama da arquitetura (Excalidraw e SVG)
├── Diagrama UML - Caso de Uso/          Diagrama de casos de uso
├── Diagramas BPMN/                      Processos de negócio (.bpmn e SVG)
└── EduConecta_projeto/
    ├── compose.yaml                     Arranque de todos os serviços
    ├── compose.debug.yaml               Reabre as portas dos serviços (depuração)
    ├── .env.example                     Variáveis de ambiente necessárias
    ├── backend/
    │   ├── gateway/                     API Gateway
    │   └── services/                    auth, escolar, assiduidade, diario, comunicados, notificacoes
    ├── docs/                            Planos de implementação (fases 1 e 2, API Gateway)
    ├── postman/                         Coleção e ambiente do Postman
    ├── testes_manuais/                  Scripts de integração
    └── EduConecta_Arquitetura_Handoff.pdf
```

Cada serviço segue a mesma organização: `app.py`, `controllers/` (rotas HTTP), `models/` (acesso aos dados), `utils/`, `tests/` e `openapi.yaml`.

## Processos de negócio (BPMN)

Os principais processos foram modelados em BPMN 2.0 e descrevem o funcionamento pretendido; a tabela [Estado do projeto](#estado-do-projeto) indica o que já está implementado. Clica numa imagem para a abrir em tamanho real e fazer zoom. Os ficheiros `.bpmn` originais estão em [`Diagramas BPMN/BPMN`](Diagramas%20BPMN/BPMN) e podem ser abertos no [bpmn.io](https://demo.bpmn.io) ou no Camunda Modeler.

### 1. Conta e primeiro acesso

O administrador cria a conta do encarregado de educação. O sistema gera uma palavra-passe temporária e envia-a por email. No primeiro início de sessão, o encarregado é obrigado a definir uma nova palavra-passe.

[![Conta e primeiro acesso](Diagramas%20BPMN/SVG/Conta%20e%20primeiro%20acesso.svg)](Diagramas%20BPMN/SVG/Conta%20e%20primeiro%20acesso.svg)

### 2. Ano letivo e inscrições

Configuração da instituição no início do ano letivo: criação de salas e turmas, associação de profissionais e inscrição de alunos, com criação automática da conta do encarregado quando necessário.

[![Ano letivo e inscrições](Diagramas%20BPMN/SVG/Ano%20letivo%20e%20inscricoes.svg)](Diagramas%20BPMN/SVG/Ano%20letivo%20e%20inscricoes.svg)

### 3. Faltas e justificações

O docente regista as faltas e o encarregado é notificado. O encarregado tem três dias úteis para submeter uma justificação com observações e anexo, que o diretor de turma aprova ou rejeita.

[![Faltas e justificações](Diagramas%20BPMN/SVG/Faltas%20e%20justificacoes.svg)](Diagramas%20BPMN/SVG/Faltas%20e%20justificacoes.svg)

### 4. Acompanhamento diário

A auxiliar regista a entrada, as refeições, o descanso, a higiene e a saída da criança. Situações relevantes são escaladas para o educador, e no fim do dia o encarregado recebe o resumo.

[![Acompanhamento diário](Diagramas%20BPMN/SVG/Acompanhamento%20diario.svg)](Diagramas%20BPMN/SVG/Acompanhamento%20diario.svg)

### 5. Comunicados

O docente ou educador publica um comunicado para uma sala, turma ou grupo.

[![Comunicados](Diagramas%20BPMN/SVG/Comunicados.svg)](Diagramas%20BPMN/SVG/Comunicados.svg)

## Equipa

| Nome | Número |
|---|---|
| Joel | 28001 |
| Fábio | 20079 |
| Emma | 37847 |

**Docente:** Bruno Lima
