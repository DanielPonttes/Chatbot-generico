# Especificações do projeto

Esta pasta reúne as especificações executáveis das etapas de implementação do
agente de notificações. Cada especificação deve registrar o objetivo, o
escopo, as decisões técnicas, os passos de execução, os critérios de aceite e
o plano de rollback.

## Convenções

- Os arquivos são numerados pela ordem recomendada de execução.
- `Draft` significa que a especificação está pronta para revisão; `Ready` que
  pode ser executada; `In progress` que está em execução; e `Accepted` que os
  critérios de aceite foram comprovados.
- Nenhuma especificação deve conter credenciais, tokens ou dados pessoais
  reais. Use variáveis de ambiente e valores fictícios nos exemplos.
- Os resultados de benchmark e os logs de execução devem ficar fora do
  controle de versão, salvo quando houver uma decisão explícita de preservar
  um relatório resumido.

## Índice

| ID | Especificação | Status |
| --- | --- | --- |
| SPEC-001 | [Runtime local com Ollama e RTX 5090](01-runtime-local-ollama.md) | Draft |
| SPEC-002 | [Segurança e contratos da API pública](02-public-api-security-and-contracts.md) | Accepted |

## Ordem da primeira etapa

1. Validar o host com a RTX 5090 e o serviço Ollama.
2. Baixar e aquecer o modelo local escolhido.
3. Configurar o chatbot para usar exclusivamente o provider Ollama.
4. Executar os smoke tests de chat e de geração proativa.
5. Medir latência, throughput e uso da GPU antes de liberar a etapa.
