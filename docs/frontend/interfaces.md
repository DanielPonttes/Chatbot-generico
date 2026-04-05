# Documentação do Frontend

A interface do usuário é composta por páginas HTML estáticas servidas pelo FastAPI, utilizando Vanilla JS e CSS (com Tailwind via CDN).

## 1. Chat Principal (`index.html`)
Localização: `/`

Interface de chat padrão "estilo WhatsApp/ChatGPT".

### Funcionalidades
- **Histórico**: Exibe mensagens trocadas na sessão atual.
- **Configuração**: Botão de engrenagem no header abre um modal.
    - Permite selecionar o **Modelo LLM** (Gemini 3 Flash/Pro).
    - A escolha é salva em memória JS e enviada em cada requisição `/chat`.
- **Navegação**: Link para a tela de Notificações.

## 2. Teste de Notificações (`notifications.html`)
Localização: `/notifications`

Interface dedicada para testar a geração de mensagens proativas (push notifications).

### Layout
- **Estilo**: Dark Mode moderno com cartões translúcidos (Glassmorphism).
- **Configuração**:
    - **Dropdown Persona**: Seleciona o tom do bot.
    - **Dropdown Perfil Alvo**: Seleciona o tipo de usuário.
    - **Botão Configurar**: Abre um modal com:
      - override de modelo
      - override de system prompt
      - toggle de `use_rag`
      - autocomplete de sala
      - autocomplete de sensor
      - autocomplete de pessoa
- **Exibição**:
    - Mostra a notificação gerada em um card.
    - Exibe o modelo efetivamente utilizado na geração.
    - Exibe um resumo do contexto aplicado quando a resposta foi enriquecida com dados reais.
- **Avaliação**:
    - Permite aprovar ou reprovar a notificação.
    - Persiste as avaliações e exibe uma lista de notificações salvas.

### Fluxo de Uso
1. Usuário seleciona Persona e Perfil.
2. Opcionalmente abre o modal de configuração para escolher modelo, prompt e contexto operacional.
3. Se selecionar contexto real, a UI consulta:
   - `/integrations/context/rooms`
   - `/integrations/context/sensors`
   - `/integrations/context/people`
4. Clica em "Gerar Notificação".
5. O JS envia `POST /chat/proactive` com os IDs e overrides selecionados.
6. Exibe a resposta e, quando aplicável, o `context_summary`.

### Cobertura Automatizada

A tela `/notifications` possui cobertura E2E com Playwright para:

- bootstrap inicial da página
- configuração contextual em viewport menor
- persistência de feedback aprovado
- tratamento de erro ao gerar a notificação

Arquivos principais:

- `tests/e2e/notifications.spec.js`
- `tests/e2e/helpers/notifications-mocks.js`

## Tecnologias
- **HTML5/CSS3**
- **TailwindCSS** (CDN)
- **Lucide Icons** (Ícones SVG)
- **Vanilla JavaScript** (Sem frameworks reativos complexos)
