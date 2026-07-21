# Cruzamento: Missões do Spec (PDF) × API Spring Boot

Data: 2026-07-20
Fontes:
- Spec: `Missões PROCEL - Página1.pdf` (64 missões)
- API: `GET https://procel.servehttp.com/api/missoes` (33 registros: 30 ativos + 3 inativos de teste)

## Resumo

| Métrica | Valor |
| --- | --- |
| Missões no PDF | 64 |
| Missões ativas na API | 30 |
| Presentes em ambos | **26 (100% das Individuais do PDF)** |
| Ausentes na API | **38** (11 Sala + 16 Curso + 11 Semestrais) |
| Extras na API (fora do PDF) | 4 |
| Divergências de XP (presentes) | **nenhuma** |
| Registros inativos (lixo de teste) | 3 |

## ✅ Presentes (26) — todas as Missões Individuais do PDF

Todas com XP idêntico ao spec (campo `value` da API = XP do PDF):

Último a Apagar (20), Sala Vazia Luz Off (20), Luz na Medida (25), AC Inteligente (25),
Intervalo Fresco Natural (25), Aula com Luz Natural (25), Checagem de Corredor (30),
Aula Econômica (35), Verificação Inicial (15), Controle de Porta (20),
Detetive de Sala Quente (15), Detetive de Sala Fria (15), Relato Coerente (20),
Power Hour (40), Turno Sem AC (40), Monitor de Luz (20), Auditor do Andar (40),
Minimizar Pico (30), Sala Eco-estudo (30), Chegada Consciente (30), Mudança Visível (30),
Sem Sobras (30), Múltiplas Salas Eficientes (40), Acompanhando o Gráfico (15),
Preferência Eficiente (20), Reporte de Ocupação (15).

## ❌ Ausentes na API (38)

### Missões Coletivas — alvo Sala (11)
Sala Sem Fantasma (90XP/10), Virada de Turno Perfeita (80/8), Aula Eficiente (80/8),
Luz Natural Diurna (60/6), AC na Faixa (90/10), Semana Sem Alertas (60/6),
Pico Domado (90/10), Sala Verde (80/8), Dia 100% Eco (60/6),
Semana do Conforto (80/8), Semestre em Miniatura (90/10).

### Missões Coletivas — alvo Curso (16)
Corredor da Sala (90/10), Corredor Verde (90/10), Desafio Curso vs Curso (100/12),
Top 3 Salas do Curso (80/8), Semana sem Fantasmas do Curso (90/10), Turno Dourado (90/10),
Dia Verde do Curso (60/6), Curso Sem Pico Desnecessário (100/12),
Rotina Fechamento do Curso (100/12), Semana da Luz Natural do Curso (80/8),
Andar Campeão (100/12), Zero Top Waster (70/7), Semana Piloto do Curso (100/12),
Curso Estável (100/12), Curso Sem Noite Ligada (90/10), Curso Top 3 do Prédio (120/14).

### Missões Semestrais (11)
Guardião de Salas (300XP/50 + badge), Semestre Ativo (250/30), Sala de Confiança (300/50 + badge),
Eco Regular (200/20), Sem Fantasma Pessoal (200/20 + badge), Quiz Master (250/30 + badge),
Sala Sem Fantasmas (300/50 + badge), Sala Top 10 (300/50 + badge),
Curso Referência (400/70 + badge), Curso Sem Vermelho (350/60), Rotina Forte do Curso (400/70 + badge).

## ➕ Extras na API, fora do PDF (4)

Missões ativas que não constam no spec — candidatas a inclusão na próxima revisão do PDF:

| Título | XP (value) |
| --- | --- |
| Elevador Zero | 35 |
| Turno Eficiente | 40 |
| Semana da Escada | 40 |
| Insight Aplicado | 60 |

## 🧪 Lixo de teste na API (3, inativas)

`API smoke test expirable mission 7a3507b4`, `API smoke test inactive mission 7a3507b4`,
`API smoke test mission updated 7a3507b4` — resíduos dos smoke tests E2E; inofensivos (ativo=false).

## Observações de modelo de dados

- A API expõe `tipo` apenas como `Individual` — não há valores `Sala`, `Curso` ou `Semestral`
  cadastrados ainda, o que explica as 38 ausências.
- O campo `value` corresponde ao XP do PDF; **a Moeda (coins) do spec não tem campo na API**.
- As Semestrais com badge (ex.: "Guardião de Salas") não têm representação de badge na API.
- O chatbot já está preparado para consumir este catálogo via `GET /api/missoes`
  (endpoint `missoes_list` no catálogo de integrações).
