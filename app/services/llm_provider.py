"""
Providers LLM para geração de respostas.

Implementa uma interface abstrata e dois providers concretos:
- OllamaProvider: execução local via Ollama (gratuito)
- HuggingFaceProvider: API de inferência HuggingFace (gratuito com limites)
"""

import logging
from abc import ABC, abstractmethod
from typing import Literal

import httpx

from app.core.config import settings
try:
    import google.generativeai as genai
except ImportError:
    genai = None

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """Exceção base para erros de providers LLM."""
    pass


class ProviderNotAvailableError(LLMProviderError):
    """Provider não está disponível ou acessível."""
    pass


class ModelNotFoundError(LLMProviderError):
    """Modelo especificado não foi encontrado."""
    pass


class LLMProvider(ABC):
    """
    Interface abstrata para providers de LLM.
    
    Define o contrato que todos os providers devem seguir.
    """
    
    @property
    @abstractmethod
    def name(self) -> Literal["ollama", "huggingface", "google"]:
        """Nome do provider."""
        pass
    
    @property
    @abstractmethod
    def model(self) -> str:
        """Nome do modelo em uso."""
        pass
    
    @abstractmethod
    async def generate(self, prompt: str, history: list[dict] | None = None, model_override: str | None = None) -> str:
        """
        Gera uma resposta para o prompt dado.
        
        Args:
            prompt: Mensagem do usuário
            history: Histórico de mensagens no formato [{"role": "user"|"assistant", "content": "..."}]
        
        Returns:
            Resposta gerada pelo modelo
        
        Raises:
            ProviderNotAvailableError: Se o provider não estiver acessível
            ModelNotFoundError: Se o modelo não for encontrado
        """
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Verifica se o provider está disponível e respondendo."""
        pass


class OllamaProvider(LLMProvider):
    """
    Provider para Ollama - execução local de modelos LLM.
    
    O Ollama deve estar instalado e rodando localmente.
    Instalação: https://ollama.ai/
    
    Modelos recomendados (leves):
    - qwen2.5:0.5b  (~400MB, mais leve)
    - qwen2.5:1.5b  (~1GB, melhor qualidade)
    - llama3.2:1b   (~700MB, bom geral)
    """
    
    def __init__(
        self,
        base_url: str = settings.ollama_base_url,
        model_name: str = settings.ollama_model,
        timeout: float = 120.0,  # Modelos pequenos podem demorar na primeira execução
    ):
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)
    
    @property
    def name(self) -> Literal["ollama", "huggingface"]:
        return "ollama"
    
    @property
    def model(self) -> str:
        return self._model_name
    
    async def generate(self, prompt: str, history: list[dict] | None = None, model_override: str | None = None) -> str:
        """
        Gera resposta usando a API do Ollama.
        
        Usa o endpoint /api/chat para suportar histórico de conversa.
        """
        # Monta as mensagens no formato esperado pelo Ollama
        messages = []
        
        # Adiciona system prompt se configurado
        if settings.bot_system_prompt:
            messages.append({
                "role": "system",
                "content": settings.bot_system_prompt,
            })
        
        # Adiciona histórico se houver
        if history:
            messages.extend(history)
        
        # Adiciona a mensagem atual
        messages.append({
            "role": "user",
            "content": prompt,
        })
        
        # Usa o modelo override se fornecido, caso contrário usa o padrão
        target_model = model_override if model_override else self._model_name

        if model_override:
            logger.info(f"Usando modelo override no Ollama: {model_override}")
        
        try:
            response = await self._client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": target_model,
                    "messages": messages,
                    "stream": False,  # Resposta completa de uma vez
                },
            )
            
            if response.status_code == 404:
                raise ModelNotFoundError(
                    f"Modelo '{target_model}' não encontrado. "
                    f"Execute: ollama pull {target_model}"
                )
            
            response.raise_for_status()
            data = response.json()
            
            return data.get("message", {}).get("content", "").strip()
            
        except httpx.ConnectError:
            raise ProviderNotAvailableError(
                "Não foi possível conectar ao Ollama. "
                "Verifique se o Ollama está instalado e rodando. "
                "Execute: ollama serve"
            )
        except httpx.TimeoutException:
            raise ProviderNotAvailableError(
                f"Timeout ao aguardar resposta do Ollama (>{self._timeout}s). "
                "O modelo pode estar carregando. Tente novamente."
            )
    
    async def is_available(self) -> bool:
        """Verifica se o Ollama está rodando e o modelo está disponível."""
        try:
            # Verifica se o servidor está rodando
            response = await self._client.get(f"{self._base_url}/api/tags")
            if response.status_code != 200:
                return False
            
            # Verifica se o modelo está disponível
            data = response.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            
            # Ollama pode retornar "qwen2.5:0.5b" ou "qwen2.5:0.5b-latest"
            model_base = self._model_name.split(":")[0]
            return any(model_base in m for m in models)
            
        except Exception as e:
            logger.debug(f"Ollama not available: {e}")
            return False
    
    async def close(self):
        """Fecha o cliente HTTP."""
        await self._client.aclose()


class GoogleGeminiProvider(LLMProvider):
    """
    Provider para Google Gemini via google-generativeai SDK.
    
    Requer API Key (GEMINI_API_KEY).
    """
    
    def __init__(
        self,
        api_key: str | None = settings.gemini_api_key,
        model_name: str = settings.gemini_model,
        timeout: float = 60.0,
    ):
        if not genai:
            raise ImportError(
                "Biblioteca 'google-generativeai' não instalada. "
                "Adicione ao requirements.txt."
            )
            
        if not api_key:
            raise ValueError(
                "API Key do Gemini não configurada. "
                "Defina a variável de ambiente GEMINI_API_KEY."
            )
        
        genai.configure(api_key=api_key)
        self._model_name = model_name
        self._timeout = timeout
        
        # O SDK não precisa de um cliente persistente da mesma forma que http/ollama
        # mas configuramos o modelo aqui
        self._model = genai.GenerativeModel(model_name)
    
    @property
    def name(self) -> Literal["ollama", "huggingface", "google"]:
        return "google"
    
    @property
    def model(self) -> str:
        return self._model_name
    
    async def generate(self, prompt: str, history: list[dict] | None = None, model_override: str | None = None) -> str:
        """
        Gera resposta usando o SDK do Gemini.
        """
        try:
            # Decide qual modelo usar
            if model_override:
                logger.info(f"Usando modelo override no Gemini: {model_override}")
                active_model = genai.GenerativeModel(model_override)
            else:
                active_model = self._model
            # Converte histórico para o formato do Gemini
            chat_history = []
            if settings.bot_system_prompt:
                 # system prompt é tratado na configuração ou como primeira mensagem dependendo da versão
                 # Para simplificar e compatibilidade, vamos injetar no início se possível, 
                 # mas o SDK do genai tem suporte específico para system instructions em versões recentes.
                 # Vamos usar uma abordagem simples de append por enquanto ou usar o system_instruction se disponível no init.
                 pass

            # O SDK gerencia o histórico se usarmos start_chat, mas aqui recebemos o histórico a cada request.
            # Convertemos nosso formato (role: user/assistant) para o formato do Gemini (role: user/model)
            if history:
                for msg in history:
                    role = "user" if msg["role"] == "user" else "model"
                    chat_history.append({
                        "role": role,
                        "parts": [msg["content"]],
                    })
            
            # Inicia chat com histórico
            chat = active_model.start_chat(history=chat_history)
            
            # Envia mensagem
            # system prompt pode ser concatenado se o modelo não suportar system instruction nativamente no init
            final_prompt = prompt
            if settings.bot_system_prompt and not history: # Injeta apenas se for começo ou não tiver histórico preservado pelo SDK
                 # Nota: start_chat mantem estado, mas aqui estamos recriando a cada request.
                 # Idealmente, o system prompt deveria ir na instrução do modelo, mas vamos concatenar para garantir.
                 # Refinamento: Se o modelo suportar, melhor. No GenerativeModel(system_instruction=...)
                 pass
            
            response = await chat.send_message_async(final_prompt)
            return response.text.strip()
            
        except Exception as e:
            # Captura erros específicos do SDK se necessário
            logger.error(f"Erro no Gemini: {e}")
            if "404" in str(e) or "not found" in str(e).lower():
                 raise ModelNotFoundError(f"Modelo {self._model_name} não encontrado.")
            raise ProviderNotAvailableError(f"Erro ao acessar Gemini: {e}")

    async def is_available(self) -> bool:
        """Tenta listar modelos para verificar acesso."""
        try:
            # Lista modelo simples para teste de credencial
            # genai.list_models() retorna um iterador
            next(genai.list_models())
            return True
        except Exception:
            return False

    async def close(self):
        # SDK não requer gerenciamento de conexão explicito
        pass


class HuggingFaceProvider(LLMProvider):
    """
    Provider para HuggingFace Inference API.
    
    Requer token de autenticação (HF_TOKEN).
    Camada gratuita tem limites de uso.
    
    Obtenha seu token em: https://huggingface.co/settings/tokens
    """
    
    INFERENCE_API_URL = "https://api-inference.huggingface.co/models"
    
    def __init__(
        self,
        token: str | None = settings.hf_token,
        model_name: str = settings.hf_model,
        timeout: float = 60.0,
    ):
        if not token:
            raise ValueError(
                "Token HuggingFace não configurado. "
                "Defina a variável de ambiente HF_TOKEN. "
                "Obtenha seu token em: https://huggingface.co/settings/tokens"
            )
        
        self._token = token
        self._model_name = model_name
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
        )
    
    @property
    def name(self) -> Literal["ollama", "huggingface"]:
        return "huggingface"
    
    @property
    def model(self) -> str:
        return self._model_name
    
    async def generate(self, prompt: str, history: list[dict] | None = None, model_override: str | None = None) -> str:
        """
        Gera resposta usando a API de Inferência do HuggingFace.
        
        Nota: A API de inferência gratuita é simplificada e pode não suportar
        todos os recursos de chat avançados.
        """
        # Monta o prompt incluindo histórico básico
        full_prompt = ""
        
        # Adiciona system prompt
        if settings.bot_system_prompt:
            full_prompt += f"[Sistema]: {settings.bot_system_prompt}\n\n"
        
        # Adiciona histórico resumido
        if history:
            for msg in history[-4:]:  # Últimas 4 mensagens para não estourar contexto
                role = "Usuário" if msg["role"] == "user" else "Assistente"
                full_prompt += f"[{role}]: {msg['content']}\n"
        
        # Adiciona mensagem atual
        full_prompt += f"[Usuário]: {prompt}\n[Assistente]:"
        
        try:
            response = await self._client.post(
                f"{self.INFERENCE_API_URL}/{self._model_name}",
                json={
                    "inputs": full_prompt,
                    "parameters": {
                        "max_new_tokens": 256,
                        "temperature": 0.7,
                        "do_sample": True,
                        "return_full_text": False,
                    },
                },
            )
            
            if response.status_code == 401:
                raise ProviderNotAvailableError(
                    "Token HuggingFace inválido ou expirado. "
                    "Verifique seu HF_TOKEN."
                )
            
            if response.status_code == 404:
                raise ModelNotFoundError(
                    f"Modelo '{self._model_name}' não encontrado no HuggingFace."
                )
            
            if response.status_code == 503:
                raise ProviderNotAvailableError(
                    f"Modelo '{self._model_name}' está carregando. "
                    "Aguarde alguns segundos e tente novamente."
                )
            
            response.raise_for_status()
            data = response.json()
            
            # A resposta pode vir em diferentes formatos
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("generated_text", "").strip()
            elif isinstance(data, dict):
                return data.get("generated_text", "").strip()
            
            return str(data).strip()
            
        except httpx.ConnectError:
            raise ProviderNotAvailableError(
                "Não foi possível conectar à API do HuggingFace. "
                "Verifique sua conexão com a internet."
            )
        except httpx.TimeoutException:
            raise ProviderNotAvailableError(
                "Timeout ao aguardar resposta do HuggingFace."
            )
    
    async def is_available(self) -> bool:
        """Verifica se a API do HuggingFace está acessível."""
        try:
            # Faz uma requisição simples para verificar conectividade
            response = await self._client.get(
                f"{self.INFERENCE_API_URL}/{self._model_name}",
            )
            # 200 = ok, 503 = modelo carregando (mas API funciona)
            return response.status_code in (200, 503)
        except Exception as e:
            logger.debug(f"HuggingFace not available: {e}")
            return False
    
    async def close(self):
        """Fecha o cliente HTTP."""
        await self._client.aclose()


# ==========================================
# Factory para criar o provider correto
# ==========================================

_provider_instance: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    """
    Factory que retorna o provider LLM configurado.
    
    Usa o valor de LLM_PROVIDER nas configurações para decidir
    qual provider instanciar.
    
    Returns:
        Instância do provider configurado
    
    Raises:
        ValueError: Se o provider configurado for inválido ou não puder ser criado
    """
    global _provider_instance
    
    if _provider_instance is not None:
        return _provider_instance
    
    provider_name = settings.llm_provider.lower()
    
    if provider_name == "ollama":
        logger.info(f"Inicializando Ollama provider com modelo: {settings.ollama_model}")
        _provider_instance = OllamaProvider()
    
    elif provider_name == "huggingface":
        if not settings.hf_token:
            raise ValueError(
                "HuggingFace selecionado mas HF_TOKEN não configurado. "
                "Defina HF_TOKEN no .env ou use LLM_PROVIDER=ollama"
            )
        logger.info(f"Inicializando HuggingFace provider com modelo: {settings.hf_model}")
        _provider_instance = HuggingFaceProvider()

    elif provider_name == "google":
        if not settings.gemini_api_key:
             raise ValueError(
                "Google Gemini selecionado mas GEMINI_API_KEY não configurada. "
                "Defina GEMINI_API_KEY no .env"
            )
        logger.info(f"Inicializando Gemini provider com modelo: {settings.gemini_model}")
        _provider_instance = GoogleGeminiProvider()
    
    else:
        raise ValueError(
            f"Provider '{provider_name}' não reconhecido. "
            "Use 'ollama', 'huggingface' ou 'google'."
        )
    
    return _provider_instance


async def close_provider():
    """Fecha o provider e libera recursos."""
    global _provider_instance
    if _provider_instance is not None:
        await _provider_instance.close()
        _provider_instance = None
