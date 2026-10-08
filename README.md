# EduConecta
 
Plataforma de comunicação entre instituições de ensino (creche, pré-escolar e ensino básico) e as famílias, desenvolvida com uma arquitetura de microserviços.
 
> Trabalho prático da unidade curricular **Arquiteturas e Integração de Sistemas**, Mestrado em Engenharia Informática, Escola Superior de Tecnologia do IPCA.
 
---
 
## Índice
 
- [Sobre o projeto](#sobre-o-projeto)
- [Perfis de utilizador](#perfis-de-utilizador)
- [Arquitetura](#arquitetura)
- [Microserviços](#microserviços)
- [Tecnologias](#tecnologias)
- [Processos de negócio (BPMN)](#processos-de-negócio-bpmn)
- [Equipa](#equipa)
---
 
## Sobre o projeto
 
A comunicação entre a escola e os encarregados de educação está muitas vezes dispersa por papel, telefone, email e grupos de mensagens. Isso dificulta o acompanhamento das crianças e o registo de informação importante.
 
O **EduConecta** reúne essa comunicação numa única plataforma:
 
- **Faltas e justificações:** o docente regista as faltas, o encarregado de educação é notificado e pode submeter uma justificação com observações e anexo, e o diretor de turma aprova ou rejeita.
- **Acompanhamento diário:** na creche e no pré-escolar, as auxiliares registam refeições, descanso e higiene, e o encarregado consulta o resumo do dia.
- **Comunicados:** docentes e educadores publicam comunicados para uma sala, turma ou grupo, com confirmação de leitura opcional.
- **Gestão escolar:** o administrador configura o ano letivo, as salas, as turmas, os alunos e as respetivas associações.
## Perfis de utilizador
 
| Perfil | Acesso |
|---|---|
| **Administrador** | Configuração da instituição: anos letivos, salas, turmas, alunos, contas e perfis. |
| **Docente / Diretor de turma** | Registo de faltas, decisão sobre justificações e publicação de comunicados. |
| **Educador / Auxiliar de ação educativa** | Acompanhamento diário das crianças da sua sala. |
| **Encarregado de educação** | Consulta de informação dos seus educandos, submissão de justificações e leitura de comunicados. |
 
## Arquitetura
 
![Arquitetura do EduConecta]
 
A solução segue o padrão de **microserviços** e está alojada na **AWS**:
 
- **Front end:** aplicação React servida pelo Amazon CloudFront a partir de um bucket S3. O CloudFront encaminha os pedidos `/api` para o cluster.
- **Cluster Kubernetes (k3s em EC2):** cada microserviço corre no seu próprio container.
- **API Gateway (YARP):** ponto único de entrada da API. Valida o token JWT e encaminha cada pedido para o serviço responsável.
- **Comunicação síncrona:** APIs REST sobre HTTPS, documentadas com OpenAPI.
- **Comunicação assíncrona:** eventos publicados no RabbitMQ (por exemplo, falta registada, justificação decidida, comunicado publicado) e consumidos pelo serviço de Notificações.
- **Database per Service:** cada microserviço tem a sua própria base de dados lógica no MongoDB Atlas e credenciais próprias, com acesso apenas a essa base de dados. As credenciais são guardadas em Kubernetes Secrets.
## Microserviços
 
| Serviço | Responsabilidade |
|---|---|
| **Auth** | Contas, perfis, palavra-passe temporária, autenticação e emissão de JWT |
| **Gestão Escolar** | Anos letivos, salas, turmas, alunos, inscrições e associações |
| **Assiduidade** | Faltas e justificações 
| **Diário** | Registos diários da creche e do pré-escolar | 
| **Comunicados** | Publicação e leitura de comunicados |
| **Notificações** | Consumo de eventos, envio de emails e notificações na plataforma | 
 
## Tecnologias
 
| Área | Tecnologia |
|---|---|
| Front end | React |
| Back end | .NET (ASP.NET Core Web API) |
| API Gateway | YARP |
| Base de dados | MongoDB (MongoDB Atlas) |
| Mensagens assíncronas | RabbitMQ (MassTransit) |
| Containers e orquestração | Docker, Kubernetes (k3s) |
| Cloud | AWS: EC2, S3, CloudFront, SES, ECR, CloudWatch |
| Documentação da API | OpenAPI (Swagger) |
| Testes | Postman |
 
## Processos de negócio (BPMN)
 
Os principais processos foram modelados em BPMN 2.0. Clica numa imagem para a abrir em tamanho real e fazer zoom. Os ficheiros `.bpmn` originais estão em [`docs/bpmn/src`](docs/bpmn/src) e podem ser abertos no [bpmn.io](https://demo.bpmn.io) ou no Camunda Modeler.
 
### 1. Conta e primeiro acesso
 
O administrador cria a conta do encarregado de educação. O sistema gera uma palavra-passe temporária e envia-a por email. No primeiro início de sessão, o encarregado é obrigado a definir uma nova palavra-passe.
 
### 2. Ano letivo e inscrições
 
Configuração da instituição no início do ano letivo: criação de salas e turmas, associação de profissionais e inscrição de alunos, com criação automática da conta do encarregado quando necessário.
 
### 3. Faltas e justificações
 
O docente regista as faltas e o encarregado é notificado. O encarregado tem três dias úteis para submeter uma justificação com observações e anexo, que o diretor de turma aprova ou rejeita.
 
 
### 4. Acompanhamento diário
 
A auxiliar regista a entrada, as refeições, o descanso, a higiene e a saída da criança. Situações relevantes são escaladas para o educador, e no fim do dia o encarregado recebe o resumo.
 
### 5. Comunicados
 
O docente ou educador publica um comunicado para uma sala, turma ou grupo.
 
## Equipa
 
| Nome | Número |
|---|---|
| Joel | 28001 |
| Fábio | 20079 |
| Emma | 37847 |

 
**Docente:** Bruno Lima
