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
    - **Botão Configurar**: Permite override manual do Modelo LLM e System Prompt customizado.
- **Exibição**:
    - Mostra a notificação gerada em um card simulando uma interface móvel.
    - Exibe o modelo que foi efetivamente utilizado na geração.

### Fluxo de Uso
1. Usuário seleciona Persona e Perfil.
2. Clica em "Gerar Notificação".
3. JS envia POST para `/chat/proactive` com os IDs selecionados.
4. Exibe a resposta.

## Tecnologias
- **HTML5/CSS3**
- **TailwindCSS** (CDN)
- **Lucide Icons** (Ícones SVG)
- **Vanilla JavaScript** (Sem frameworks reativos complexos)
