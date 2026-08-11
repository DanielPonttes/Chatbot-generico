"""
Serviço de Personas para mensagens proativas.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.llm_provider import get_llm_provider, LLMProviderError
from app.services.proactive_context import get_proactive_operational_context_service
from app.rag.retriever import get_relevant_context

logger = logging.getLogger(__name__)

# Caminho do YAML com os tipos de notificação.
# Resolve relativo a este arquivo para funcionar independente do cwd.
_NOTIFICATION_TYPES_PATH = Path(__file__).with_name("notification_type.yaml")


# ---------------------------------------------------------------------------
# Dataclasses de domínio (Persona e TargetProfile permanecem dataclasses —
# são simples, estáticos e não precisam de validação em runtime)
# ---------------------------------------------------------------------------

@dataclass
class Persona:
    id: str
    name: str
    description: str
    system_prompt: str


@dataclass
class TargetProfile:
    id: str
    name: str
    description: str
    context: str


@dataclass
class ProactiveMessageResult:
    message: str
    context_summary: str | None = None
    prompt_used: str | None = None


class PersonaNotFoundError(ValueError):
    """A persona solicitada não existe no catálogo local."""


class NotificationTypeNotFoundError(ValueError):
    """O template de notificação solicitado não existe no catálogo local."""


class NotificationContextValidationError(ValueError):
    """O contexto não contém as variáveis exigidas pelo template."""


# ---------------------------------------------------------------------------
# NotificationType como Pydantic BaseModel
# ---------------------------------------------------------------------------

class NotificationType(BaseModel):
    """
    Define um subtipo de notificação proativa.

    Carregado a partir de notification_types.yaml e validado pelo Pydantic
    na inicialização da aplicação — erros de conteúdo no YAML são detectados
    antes da primeira requisição chegar.
    """

    id: str = Field(
        ...,
        min_length=1,
        description="Identificador único do tipo (ex: 'reengajamento_streak').",
    )
    name: str = Field(
        ...,
        min_length=1,
        description="Nome legível para exibição no frontend.",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Descrição do objetivo e caso de uso do tipo.",
    )
    category: str = Field(
        ...,
        min_length=1,
        description="Categoria funcional do documento de notificações.",
    )
    subtype: str = Field(
        ...,
        min_length=1,
        description="Subtipo funcional exibido para integrações.",
    )
    system_prompt_template: str = Field(
        ...,
        min_length=10,
        description=(
            "Template do system prompt. Use {variavel} para slots dinâmicos. "
            "Variáveis opcionais não precisam estar em required_context_vars — "
            "o _SafeDict lida com ausências sem quebrar o formato."
        ),
    )
    required_context_vars: List[str] = Field(
        default_factory=list,
        description=(
            "Variáveis que DEVEM estar presentes em notification_context ao chamar este tipo. "
            "O serviço valida isso antes de chamar o LLM."
        ),
    )
    default_use_rag: bool = Field(
        default=False,
        description=(
            "Se RAG deve ser ativado por padrão para este tipo. "
            "O parâmetro use_rag da requisição tem prioridade se fornecido explicitamente."
        ),
    )

    # --- Validadores ---

    @field_validator("id")
    @classmethod
    def id_sem_espacos(cls, v: str) -> str:
        if " " in v:
            raise ValueError(
                f"O campo 'id' não pode conter espaços. Use underscores: '{v.replace(' ', '_')}'"
            )
        return v

    @field_validator("required_context_vars")
    @classmethod
    def vars_sem_chaves(cls, v: List[str]) -> List[str]:
        """Garante que as variáveis foram declaradas sem as chaves do template (sem { })."""
        for var in v:
            if "{" in var or "}" in var:
                raise ValueError(
                    f"required_context_vars deve listar nomes sem chaves. "
                    f"Use '{var.strip('{}' )}' em vez de '{var}'."
                )
        return v

    @model_validator(mode="after")
    def vars_presentes_no_template(self) -> "NotificationType":
        """
        Verifica que todas as required_context_vars aparecem de fato no template.
        Evita declarar uma variável como obrigatória mas esquecer de usá-la no prompt.
        """
        for var in self.required_context_vars:
            if f"{{{var}}}" not in self.system_prompt_template:
                raise ValueError(
                    f"A variável obrigatória '{var}' está em required_context_vars "
                    f"mas não aparece no system_prompt_template como '{{{var}}}'."
                )
        return self

    @property
    def context_variables(self) -> list[str]:
        """Retorna os slots do prompt que podem ser preenchidos pelo contexto."""
        variables = {
            field_name.split(".", 1)[0].split("[", 1)[0]
            for _, field_name, _, _ in Formatter().parse(self.system_prompt_template)
            if field_name and field_name != "user_first_name_line"
        }
        return sorted(variables)


# ---------------------------------------------------------------------------
# Carregador e validador do YAML
# ---------------------------------------------------------------------------

def _load_notification_types(path: Path = _NOTIFICATION_TYPES_PATH) -> List[NotificationType]:
    """
    Lê notification_types.yaml e valida cada entrada contra NotificationType.

    Lança erros descritivos na inicialização se o YAML estiver malformado,
    evitando que problemas de conteúdo só apareçam em runtime.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo de tipos de notificação não encontrado: {path}\n"
            f"Crie o arquivo em app/services/notification_type.yaml."
        )

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(raw, dict) or "notification_types" not in raw:
        raise ValueError(
            "O YAML deve ter uma chave raiz 'notification_types' com uma lista de tipos."
        )

    entries = raw["notification_types"]
    if not isinstance(entries, list):
        raise ValueError("'notification_types' deve ser uma lista.")

    tipos: List[NotificationType] = []
    erros: List[str] = []

    for i, entry in enumerate(entries):
        try:
            tipos.append(NotificationType(**entry))
        except Exception as e:
            # Coleta todos os erros antes de lançar, para facilitar correção do YAML
            entry_id = entry.get("id", f"<entrada #{i + 1}>")
            erros.append(f"  [{entry_id}] {e}")

    if erros:
        raise ValueError(
            f"Erros encontrados em {path.name}:\n" + "\n".join(erros)
        )

    # Verifica IDs duplicados
    ids = [t.id for t in tipos]
    duplicados = {id_ for id_ in ids if ids.count(id_) > 1}
    if duplicados:
        raise ValueError(
            f"IDs duplicados encontrados em {path.name}: {duplicados}"
        )

    logger.info(f"{len(tipos)} tipos de notificação carregados de '{path.name}'.")
    return tipos


# Carregado uma vez na inicialização do módulo.
# Se o YAML tiver erro, a aplicação falha no startup com mensagem clara.
NOTIFICATION_TYPES: List[NotificationType] = _load_notification_types()


# ---------------------------------------------------------------------------
# Personas — definem o TOM da mensagem
# ---------------------------------------------------------------------------

PERSONAS = [
    Persona(
        id="provocador",
        name="Provocador",
        description="Usa ironia leve e desafios para estimular a ação.",
        system_prompt=(
            "Você é um chatbot com personalidade Provocadora sobre eficiência energética. "
            "Seu tom é desafiador, levemente irônico e questionador. "
            "Você não dá tapinha nas costas; você desafia o usuário a provar que consegue economizar. "
            "Use frases curtas e instigantes."
        )
    ),
    Persona(
        id="motivador",
        name="Motivador",
        description="Positivo, encorajador e focado em metas.",
        system_prompt=(
            "Você é um chatbot Motivador e entusiasta da eficiência energética. "
            "Seu tom é extremamente positivo, encorajador e vibrante. "
            "Você celebra qualquer esforço e foca no impacto positivo para o planeta e para o bolso. "
            "Use emojis e linguagem inspiradora."
        )
    ),
    Persona(
        id="debochado",
        name="Debochado",
        description="Humor ácido e sarcástico, focado no absurdo do desperdício.",
        system_prompt=(
            "Você é um chatbot Debochado que não acredita no quanto as pessoas desperdiçam dinheiro/energia à toa. "
            "Seu tom é sarcástico, ácido e informal. "
            "Você faz piada com o desperdício e trata a economia como algo óbvio que o usuário está 'lentamente' percebendo. "
            "Use gírias e humor."
        )
    )
]


# ---------------------------------------------------------------------------
# Perfis-alvo — definem o CONTEXTO DO RECEPTOR
# ---------------------------------------------------------------------------

TARGET_PROFILES = [
    TargetProfile(
        id="gastao",
        name="O Gastão Sem Noção",
        description="Não economiza e não tem consciência.",
        context=(
            "O usuário desperdiça muita energia, deixa luzes acesas, banhos longos "
            "e não parece se importar com a conta ou o meio ambiente."
        )
    ),
    TargetProfile(
        id="indiferente",
        name="O Indiferente",
        description="Ignora mensagens e não interage.",
        context=(
            "O usuário recebe várias notificações mas nunca abre o app. "
            "Ele ignora os avisos e continua com seus hábitos, tratando o bot como ruído."
        )
    ),
    TargetProfile(
        id="engajado",
        name="O Engajado",
        description="Interage e busca economia.",
        context=(
            "O usuário já economiza, interage sempre com o app e busca novas formas de otimizar. "
            "Ele é um parceiro na missão de eficiência."
        )
    )
]


# ---------------------------------------------------------------------------
# Utilitário interno
# ---------------------------------------------------------------------------

class _SafeDict(dict):
    """
    dict que retorna '{chave}' para chaves ausentes em str.format_map().
    Permite variáveis opcionais no template sem causar KeyError.
    """
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


# ---------------------------------------------------------------------------
# PersonaService
# ---------------------------------------------------------------------------

class PersonaService:

    # --- Personas ---

    @staticmethod
    def get_personas() -> List[Persona]:
        return PERSONAS

    @staticmethod
    def get_persona_by_id(persona_id: str) -> Optional[Persona]:
        return next((p for p in PERSONAS if p.id == persona_id), None)

    # --- Target Profiles ---

    @staticmethod
    def get_target_profiles() -> List[TargetProfile]:
        return TARGET_PROFILES

    @staticmethod
    def get_target_profile_by_id(profile_id: str) -> Optional[TargetProfile]:
        return next((p for p in TARGET_PROFILES if p.id == profile_id), None)

    # --- Notification Types ---

    @staticmethod
    def get_notification_types() -> List[NotificationType]:
        return NOTIFICATION_TYPES

    @staticmethod
    def get_notification_type_by_id(notif_type_id: str) -> Optional[NotificationType]:
        return next((n for n in NOTIFICATION_TYPES if n.id == notif_type_id), None)

    # --- Geração ---

    @staticmethod
    async def generate_proactive_message(
        persona_id: str,
        target_profile_id: Optional[str] = None,
        persona_override: Optional[object] = None,
        model_override: Optional[str] = None,
        use_rag: Optional[bool] = None,
        room_id: Optional[str] = None,
        sensor_external_id: Optional[str] = None,
        pessoa_id: Optional[str] = None,
        notification_type_id: Optional[str] = None,
        notification_context: Optional[Dict[str, Any]] = None,
    ) -> ProactiveMessageResult:
        """
        Gera uma mensagem proativa compondo Persona + NotificationType + TargetProfile.

        Args:
            persona_id:            Tom da mensagem (obrigatório).
            target_profile_id:     Perfil do receptor (opcional).
            persona_override:      Substitui o system_prompt da persona (opcional).
            model_override:        Modelo a usar nesta chamada (opcional).
            use_rag:               Força ativar/desativar RAG. Se None, usa default_use_rag
                                   do NotificationType (ou True se não houver tipo definido).
            notification_type_id:  Subtipo de notificação (opcional; sem ele, comportamento legado).
            notification_context:  Dict com as variáveis do template do NotificationType.
        """

        # 1. Resolve Persona
        persona = PersonaService.get_persona_by_id(persona_id)
        if not persona:
            raise PersonaNotFoundError(f"Persona '{persona_id}' não encontrada.")

        persona_prompt = persona.system_prompt
        if persona_override and getattr(persona_override, "system_prompt", None):
            persona_prompt = persona_override.system_prompt

        # 2. Resolve NotificationType
        notif_type_block = ""
        effective_use_rag = use_rag  # pode ser None ainda

        if notification_type_id:
            notif_type = PersonaService.get_notification_type_by_id(notification_type_id)
            if not notif_type:
                raise NotificationTypeNotFoundError(
                    f"NotificationType '{notification_type_id}' não encontrado."
                )

            ctx = dict(notification_context or {})

            # Valida variáveis obrigatórias
            missing = [v for v in notif_type.required_context_vars if v not in ctx]
            if missing:
                raise NotificationContextValidationError(
                    f"Variáveis obrigatórias ausentes para '{notification_type_id}': {missing}"
                )

            # Monta linha opcional de nome do usuário
            ctx.setdefault("user_first_name_line", "")
            if ctx.get("user_first_name"):
                ctx["user_first_name_line"] = f"Nome do usuário: {ctx['user_first_name']}\n"

            # Preenche o template — variáveis ausentes ficam como {chave} via _SafeDict
            filled_template = notif_type.system_prompt_template.format_map(_SafeDict(ctx))
            notif_type_block = f"\n{filled_template}"

            # Decide use_rag: parâmetro explícito tem prioridade
            if effective_use_rag is None:
                effective_use_rag = notif_type.default_use_rag
        else:
            # Comportamento legado: sem tipo definido, RAG ativado por padrão
            if effective_use_rag is None:
                effective_use_rag = True

        # 3. Resolve TargetProfile
        target_context = ""
        if target_profile_id:
            target_profile = PersonaService.get_target_profile_by_id(target_profile_id)
            if target_profile:
                target_context = (
                    f"\nCONTEXTO DO USUÁRIO ALVO:\n"
                    f"Nome do Perfil: {target_profile.name}\n"
                    f"Descrição: {target_profile.context}\n"
                    "Adapte sua mensagem especificamente para este tipo de usuário."
                )

        operational_context = get_proactive_operational_context_service().build_context(
            room_id=room_id,
            sensor_external_id=sensor_external_id,
            pessoa_id=pessoa_id,
        )

        # 4. Busca contexto RAG
        rag_context = ""
        if effective_use_rag:
            rag_query = "Dicas de eficiência energética, economia e conscientização sustentável."
            try:
                retrieved_docs = get_relevant_context(rag_query, k=3)
                if retrieved_docs:
                    rag_context = (
                        "\nUse as seguintes informações reais recuperadas da base de conhecimento "
                        "para dar mais embasamento à sua mensagem:\n"
                        f"<BASE_DE_CONHECIMENTO>\n{retrieved_docs}\n</BASE_DE_CONHECIMENTO>\n"
                    )
            except Exception as e:
                logger.error(f"Erro ao buscar contexto RAG (ignorando): {e}")

        # 5. Monta prompt final
        prompt = (
            f"Atue com a seguinte persona:\n{persona_prompt}"
            f"{notif_type_block}"
            f"{target_context}"
            f"{operational_context.prompt_block}"
            f"{rag_context}\n"
            "Gere uma notificação curta (push notification) de 1 a 2 frases para o celular do usuário. "
            "Seja direto e mantenha sua personalidade intrínseca."
        )

        # 6. Chama o provider
        provider = get_llm_provider()
        try:
            message = await provider.generate(prompt, model_override=model_override)
            return ProactiveMessageResult(
                message=message,
                context_summary=operational_context.summary,
                prompt_used=prompt,
            )
        except Exception as e:
            logger.error(f"Erro ao gerar mensagem proativa para persona='{persona_id}': {e}")
            raise LLMProviderError(f"Falha na geração de mensagem: {e}")
