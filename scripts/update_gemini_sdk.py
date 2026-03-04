import re

def update_sdk(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
        
    # Replace import
    content = content.replace("import google.generativeai as genai", "from google import genai")
    
    # Replace dependency requirements error message
    content = content.replace("'google-generativeai' não instalada", "'google-genai' (google-genai) não instalada")
    
    # Replace genai.configure() logic
    # The new SDK instantiates a client: client = genai.Client(api_key=api_key)
    def repl_init(m):
        return """        if not api_key:
            raise ValueError(
                "API Key do Gemini não configurada. "
                "Defina a variável de ambiente GEMINI_API_KEY."
            )
        
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name
        self._timeout = timeout"""

    content = re.sub(r"""        if not api_key:
            raise ValueError\(
                "API Key do Gemini não configurada. "
                "Defina a variável de ambiente GEMINI_API_KEY."
            \)
        
        genai\.configure\(api_key=api_key\)
        self\._model_name = model_name
        self\._timeout = timeout
        
        # .*?
        # .*?
        self\._model = genai\.GenerativeModel\(model_name\)""", repl_init, content, flags=re.DOTALL)
        
    # Replace the generate method body
    def repl_generate(m):
        return """        try:
            target_model = model_override if model_override else self._model_name
            if model_override:
                logger.info(f"Usando modelo override no Gemini: {model_override}")
            
            # Converte histórico para o formato do Gemini
            chat_history = []
            
            # O novo SDK usa config para manter histórico se estivermos chamando o generate_content em um loop,
            # mas o novo modo suporta formatar a string de prompts. 
            # Como a aplicação envia mensagens iterativas:
            # "A conversa começa com system prompt e usa a roles permitidas"
            
            contents = []
            if settings.bot_system_prompt:
                contents.append(genai.types.Content(role="user", parts=[genai.types.Part.from_text(text=f"Instructions: {settings.bot_system_prompt}")]))
                contents.append(genai.types.Content(role="model", parts=[genai.types.Part.from_text(text="Entendido.")]))

            if history:
                for msg in history:
                    role = "user" if msg["role"] == "user" else "model"
                    contents.append(
                        genai.types.Content(
                            role=role,
                            parts=[genai.types.Part.from_text(text=msg["content"])]
                        )
                    )
            
            contents.append(
                genai.types.Content(
                    role="user",
                    parts=[genai.types.Part.from_text(text=prompt)]
                )
            )

            # Envia mensagem
            response = self._client.models.generate_content(
                model=target_model,
                contents=contents
            )
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"Erro no Gemini: {e}")
            if "404" in str(e) or "not found" in str(e).lower():
                 raise ModelNotFoundError(f"Modelo {self._model_name} não encontrado.")
            raise ProviderNotAvailableError(f"Erro ao acessar Gemini: {e}")"""

    content = re.sub(r"""        try:
            # Decide qual modelo usar.*?raise ProviderNotAvailableError\(f"Erro ao acessar Gemini: {e}"\)""", repl_generate, content, flags=re.DOTALL)

    # Replace the is_available method correctly without genai.list_models() error (now it's client.models.list())
    def repl_available(m):
        return """    async def is_available(self) -> bool:
        \"\"\"Tenta listar modelos para verificar acesso.\"\"\"
        try:
            next(self._client.models.list())
            return True
        except Exception:
            return False"""
            
    content = re.sub(r"""    async def is_available\(self\) -> bool:
        \"\"\"Tenta listar modelos para verificar acesso.\"\"\"
        try:
            # Lista modelo simples para teste de credencial
            # genai\.list_models\(\) retorna um iterador
            next\(genai\.list_models\(\)\)
            return True
        except Exception:
            return False""", repl_available, content, flags=re.DOTALL)

    with open(filepath, 'w') as f:
        f.write(content)

update_sdk('app/services/llm_provider.py')
