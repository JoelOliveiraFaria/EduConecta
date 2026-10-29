# Fase 1 — Fechar requisitos funcionais em falta

Documento para aprovação antes de começar a implementar. Cobre os gaps identificados entre o código atual e o PDF de requisitos (`Trabalho Prático_ EduConecta.pdf`).

**Confirmado com o Joel:**
- RF07 (atribuir perfil) **não entra** — perfil continua a ser definido só na criação do utilizador, como já é hoje.
- RNF09/RNF10 (deploy cloud, escalabilidade) ficam para o fim do projeto, só se sobrar tempo.
- RabbitMQ **é obrigatório** — mas entra na Fase 2 (notificações), não nesta fase.

---

## 1. `auth` — editar, desativar e eliminar utilizador (RF04, RF05, RF06)

### Novos endpoints

| Rota | Perfil | O que faz |
|---|---|---|
| `PATCH /admin/utilizadores/{conta_id}` | admin | Edita `nome`, `email` e/ou `perfil` de um utilizador existente (RF04) |
| `POST /admin/utilizadores/{conta_id}/desativar` | admin | Muda `estado` para `inativo` — reversível (RF05) |
| `POST /admin/utilizadores/{conta_id}/reativar` | admin | Volta a pôr `estado` em `ativo` — necessário para RF05 fazer sentido como "temporário" |
| `DELETE /admin/utilizadores/{conta_id}` | admin | Elimina o utilizador (RF06) |

### Regras de validação (iguais ao padrão já usado no `/admin/utilizadores` POST)
- `PATCH`: mesmo formato de validação de nome/email/perfil já existente em `criar_utilizador_com_email`; pelo menos um campo tem de ser enviado; email novo não pode colidir com outro utilizador.
- Um admin não pode desativar/eliminar a própria conta (evita ficar sem acesso de administração sem querer).
- Desativar ⇒ `estado: "inativo"`. Um utilizador inativo já falha hoje no `/me` do serviço `escolar`/`comunicados`/etc. (todos verificam `estado == "ativo"`), por isso isto propaga-se automaticamente sem mexer nos outros serviços.

### ⚠️ Decisão a confirmar: eliminar é "hard delete" ou "soft delete"?
O utilizador pode estar referenciado noutros serviços (`escolar.profissionais.utilizador_id`, `escolar.encarregados_educacao.utilizador_id`). Se apagarmos o documento de vez:
- **Opção A — soft delete (recomendo):** `estado: "eliminado"`, o documento fica na BD mas bloqueado (login, `/me`, tudo falha). Nada fica órfão, há rasto para auditoria.
- **Opção B — hard delete real:** remove o documento. Mais fiel à palavra "eliminar", mas os registos em `escolar` (ex: profissional associado a turmas) ficam a apontar para um `utilizador_id` que já não existe — nada rebenta (não há `ON DELETE CASCADE` entre serviços), mas fica "sujo".

**Proponho a Opção A.** Confirma antes de eu avançar.

---

## 2. `escolar` — eliminar aluno + abrir edição a Profissional (RF09, RF10)

### Novo endpoint

| Rota | Perfil | O que faz |
|---|---|---|
| `DELETE /alunos/{aluno_id}` | admin | Elimina o aluno (RF10) |

### Alteração de permissão existente

`PATCH /alunos/{aluno_id}` (editar aluno) hoje só deixa `admin` passar (está fora de `PERMISSOES_PESSOAIS` em `controllers/blueprint.py`). O RF09 diz que **Profissional** também deve poder editar.

Proposta: um Profissional (docente/educadora/auxiliar) só pode editar um aluno se **o aluno estiver numa turma onde esse profissional está atribuído** — segue a mesma regra que já existe para `/me/turmas/<id>/alunos` (RNF01: acesso limitado à turma). Implica:
1. Adicionar `PATCH` à lógica de permissão em `blueprint.py` (hoje é "está na lista `PERMISSOES_PESSOAIS` ou é admin"; passa a precisar de uma verificação extra dentro do próprio controller, porque depende dos dados do aluno, não só do perfil).
2. Dentro de `atualizar_aluno`: se quem está autenticado não é admin, procurar a turma do aluno e confirmar que o profissional está nela (reaproveita `modelo_turma.obter_atribuida_ao_profissional` que já existe).

### ⚠️ Decisão a confirmar: o que acontece aos registos de `diario`/`assiduidade` quando um aluno é eliminado?
Esses dois serviços têm registos próprios (diário, faltas) que referenciam `aluno_id`. Eliminar o aluno no `escolar` **não** apaga nem bloqueia nada nesses serviços — ficam registos históricos a apontar para um aluno que já não existe.

**Proponho não resolver isto agora** (é um caso de uso de sincronização entre serviços, que cabe melhor na Fase 2 com RabbitMQ — publicar um evento `aluno.eliminado` que os outros serviços podem escutar). Fica assinalado como limitação conhecida.

---

## 3. `assiduidade` — fluxo de justificação de faltas (RF18, RF20, RF21, RF22)

É o maior gap — hoje o serviço só marca `presente` / `falta` / `por_marcar`, não existe nenhuma noção de justificação.

### ⚠️ Decisão a confirmar: RF18 vs RF20 — são a mesma coisa ou duas vias diferentes?

O PDF tem isto, que parece contraditório:
- **RF18** "Justificar falta" → perfil **Diretor de turma** → "permitir justificar uma falta a um aluno"
- **RF20** "Submeter justificação" → perfil **Encarregado de educação** → "justificar uma falta do seu educando através da indicação de um motivo"

A minha leitura: são **dois caminhos diferentes**, não o mesmo requisito duplicado:
- **RF20–22** = fluxo normal (encarregado submete motivo → fica `pendente` → diretor de turma/educadora aprova ou rejeita)
- **RF18** = via direta institucional (ex: falta por visita de estudo, o próprio professor já sabe o motivo e marca a falta como justificada sem precisar que o encarregado submeta nada)

**Proponho implementar as duas vias** com este modelo de dados (nova coleção `justificacoes` no `assiduidade`):

```
{
  _id,
  turma_id, aluno_id, dia,          # identifica a falta
  origem: "encarregado" | "instituicao",
  motivo: str,
  estado: "pendente" | "aprovada" | "rejeitada",
  motivo_rejeicao: str | None,
  submetida_por: utilizador_id,
  submetida_em: datetime,
  decidida_por: utilizador_id | None,
  decidida_em: datetime | None,
}
```

### Novos endpoints

| Rota | Perfil | RF | O que faz |
|---|---|---|---|
| `POST /alunos/{aluno_id}/faltas/{dia}/justificacao` | Encarregado (do próprio educando) | RF20 | Submete motivo. Falha se a falta não existir, já estiver justificada, ou o prazo (3 dias úteis a contar da falta) já tiver passado. Fica `estado: "pendente"`. |
| `PUT /alunos/{aluno_id}/faltas/{dia}/justificacao/aprovar` | docente/educadora da turma | RF21 | `estado → "aprovada"` |
| `PUT /alunos/{aluno_id}/faltas/{dia}/justificacao/rejeitar` | docente/educadora da turma | RF22 | Exige `motivo_rejeicao` no corpo; `estado → "rejeitada"` |
| `POST /alunos/{aluno_id}/faltas/{dia}/justificar-institucional` | docente/educadora da turma | RF18 | Marca a falta como justificada diretamente, `origem: "instituicao"`, `estado: "aprovada"` logo à partida, sem passar por "pendente" |
| `GET /alunos/{aluno_id}/faltas/{dia}/justificacao` | encarregado do aluno, docente/educadora da turma, admin | RF19 (extensão) | Consulta o estado da justificação, se existir |

### ⚠️ Decisão a confirmar: quem é o "diretor de turma"?

O PDF trata "diretor de turma" e "educadora responsável" como papéis específicos *dentro* de uma turma — mas hoje, no nosso modelo, `turmas.profissionais_ids` é só uma lista plana, sem distinguir quem é o "responsável principal". **Proponho, para já, que qualquer profissional atribuído à turma possa aprovar/rejeitar/justificar institucionalmente** (não introduzir o conceito de "diretor de turma" como campo novo) — simplificação deliberada para não aumentar o âmbito. Se isto for importante para a disciplina, digo já e ajusto antes de começar.

### Fora de âmbito para a Fase 1 (fica para depois, assinalado)
- **Anexo na justificação** (ex: atestado) — o BPMN menciona um documento opcional. Implica upload de ficheiro, à semelhança do que já existe no `comunicados` (fotos/vídeos via GridFS). Proponho adiar para não misturar com esta fase — a justificação funciona só com texto por agora.
- **Expiração automática do prazo de 3 dias úteis** — o BPMN modela isto como um temporizador automático. Sem um agendador (cron/worker), só consigo validar o prazo *no momento da submissão* (rejeita se já passou), não fazer a falta "expirar sozinha" ao fim de 3 dias. Automação fica para quando houver infraestrutura de tarefas agendadas.

---

## Testes previstos para esta fase

Para cada endpoint novo: caso de sucesso, validação de input inválido, e o caso de permissão negada (perfil errado). Seguindo o padrão já estabelecido (pytest + mocks da camada `models/`, sem precisar de BD real).

Estimativa: ~8 testes novos em `auth`, ~4 em `escolar`, ~15–18 em `assiduidade` (é o fluxo mais complexo).

---

## Resumo do que preciso que confirmes antes de começar

1. Eliminar utilizador (`auth`) — soft delete (`estado: "eliminado"`) ou hard delete real?
2. Aceitas deixar os registos de `diario`/`assiduidade` órfãos quando um aluno é eliminado (resolvido só na Fase 2)?
3. A minha leitura de RF18 vs RF20 (duas vias: institucional direta vs. submetida pelo encarregado) está certa?
4. Aceitas que qualquer profissional da turma aprove/rejeite justificações, sem introduzir "diretor de turma" como conceito formal?
5. Aceitas adiar o anexo (atestado) e a expiração automática do prazo para depois desta fase?
