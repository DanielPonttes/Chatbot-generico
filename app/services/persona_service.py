"""
Serviço de Personas para mensagens proativas.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from app.services.llm_provider import get_llm_provider, LLMProviderError
from app.rag.retriever import get_relevant_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses de domínio
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
class NotificationType:
    id: str
    name: str
    description: str
    # Template do system prompt. Use {variavel} para slots dinâmicos.
    # O preenchimento acontece em generate_proactive_message via notification_context.
    system_prompt_template: str
    # Variáveis obrigatórias que DEVEM estar em notification_context ao chamar este tipo.
    required_context_vars: List[str] = field(default_factory=list)
    # Sugestão de uso de RAG para este tipo (pode ser sobrescrito na chamada).
    default_use_rag: bool = False


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
# Tipos de notificação — definem o OBJETIVO e as VARIÁVEIS de contexto
# ---------------------------------------------------------------------------

NOTIFICATION_TYPES = [
    # --- Grupo: Reengajamento (Win-back) ---

    NotificationType(
        id="reengajamento_streak",
        name="Alerta de Risco de Streak",
        description="Ativa aversão à perda para usuários prestes a quebrar uma sequência de dias.",
        default_use_rag=False,
        required_context_vars=["streak_days", "hours_remaining"],
        system_prompt_template=(
            "TIPO DE NOTIFICAÇÃO: Reengajamento — Risco de Streak\n"
            "\n"
            "CONTEXTO DO GATILHO:\n"
            "O usuário está prestes a perder uma sequência contínua (streak) de dias economizando energia.\n"
            "Dias consecutivos acumulados: {streak_days}\n"
            "Horas restantes para a streak quebrar: {hours_remaining}\n"
            "{user_first_name_line}"
            "\n"
            "SEU OBJETIVO:\n"
            "Gere UMA notificação push de no máximo 2 frases aplicando o tom da sua persona e que:\n"
            "- Ative o gatilho de AVERSÃO À PERDA (o usuário não quer perder o que construiu)\n"
            "- Mencione os {streak_days} dias de forma concreta\n"
            "- Proponha UMA micro-ação simples e imediata\n"
            "- Transmita urgência real sem ser alarmista\n"
            "\n"
            "RESTRIÇÕES:\n"
            "- Máximo 2 frases. Não inclua explicações, prefixos ou aspas na saída.\n"
            "- Não invente dados além dos fornecidos.\n"
            "- Não use linguagem punitiva ou de vergonha — o objetivo é motivar.\n"
            "- Máximo 2 emojis.\n"
        )
    ),

    NotificationType(
        id="reengajamento_cofre",
        name="Pontos a Expirar",
        description="Traz usuário inativo lembrando do valor acumulado com urgência de expiração.",
        default_use_rag=False,
        required_context_vars=["coins_amount", "expiry_deadline", "redemption_example"],
        system_prompt_template=(
            "TIPO DE NOTIFICAÇÃO: Reengajamento — Pontos a Expirar\n"
            "\n"
            "CONTEXTO DO GATILHO:\n"
            "O usuário está inativo e possui EcoCoins acumuladas prestes a expirar.\n"
            "Moedas prestes a expirar: {coins_amount}\n"
            "Prazo de expiração: {expiry_deadline}\n"
            "Exemplo de resgate disponível: {redemption_example}\n"
            "{user_first_name_line}"
            "\n"
            "SEU OBJETIVO:\n"
            "Gere UMA notificação push de no máximo 2 frases aplicando o tom da sua persona e que:\n"
            "- Lembre o valor concreto ({coins_amount} moedas) que o usuário já possui\n"
            "- Crie urgência real pelo prazo ({expiry_deadline})\n"
            "- Mencione o resgate específico ({redemption_example})\n"
            "- Deixe claro que a perda é evitável com uma ação simples agora\n"
            "\n"
            "RESTRIÇÕES:\n"
            "- Máximo 2 frases. Não inclua explicações, prefixos ou aspas na saída.\n"
            "- Não invente benefícios além de {redemption_example}.\n"
            "- Tom informativo e urgente, nunca ameaçador.\n"
            "- Máximo 2 emojis.\n"
        )
    ),

    NotificationType(
        id="reengajamento_winback",
        name="Surpresa de Retorno",
        description="Reativa usuários frios com novidade do app + recompensa imediata.",
        default_use_rag=True,   # RAG pode enriquecer a descrição da nova feature
        required_context_vars=["new_feature_name", "new_feature_description", "welcome_back_reward"],
        system_prompt_template=(
            "TIPO DE NOTIFICAÇÃO: Reengajamento — Surpresa de Retorno\n"
            "\n"
            "CONTEXTO DO GATILHO:\n"
            "O usuário está frio — inativo há semanas ou meses.\n"
            "Dias desde o último acesso: {days_inactive}\n"
            "Nova funcionalidade lançada: {new_feature_name} — {new_feature_description}\n"
            "Recompensa de boas-vindas: {welcome_back_reward}\n"
            "{user_first_name_line}"
            "\n"
            "SEU OBJETIVO:\n"
            "Gere UMA notificação push de no máximo 2 frases aplicando o tom da sua persona e que:\n"
            "- Abra com gancho de novidade genuína (o app evoluiu desde que saiu)\n"
            "- Mencione a recompensa {welcome_back_reward} de forma explícita\n"
            "- Crie curiosidade sem revelar tudo\n"
            "- Transmita acolhimento, NÃO cobrança pela ausência\n"
            "\n"
            "RESTRIÇÕES:\n"
            "- Máximo 2 frases. Não inclua explicações, prefixos ou aspas na saída.\n"
            "- Para usuários inativos há mais de 60 dias: tom ainda mais suave, sem urgência.\n"
            "- Máximo 2 emojis.\n"
        )
    ),

    # --- Grupo: Educativo/Engajamento (exemplo de extensibilidade) ---
    # Descomente e preencha quando for adicionar este grupo:
    #
    # NotificationType(
    #     id="educativo_dica_rapida",
    #     name="Dica Rápida de Economia",
    #     description="Entrega uma dica curta de eficiência energética baseada no RAG.",
    #     default_use_rag=True,
    #     required_context_vars=[],
    #     system_prompt_template=(
    #         "TIPO DE NOTIFICAÇÃO: Educativo — Dica Rápida\n"
    #         "..."
    #     )
    # ),
]


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
        # Novos parâmetros:
        notification_type_id: Optional[str] = None,
        notification_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Gera uma mensagem proativa compondo Persona + NotificationType + TargetProfile.

        Args:
            persona_id:            Tom da mensagem (obrigatório).
            target_profile_id:     Perfil do receptor (opcional).
            persona_override:      Substitui o system_prompt da persona (opcional).
            model_override:        Modelo a usar nesta chamada (opcional).
            use_rag:               Força ativar/desativar RAG. Se None, usa default do NotificationType
                                   (ou True se não houver NotificationType).
            notification_type_id:  Subtipo de notificação (opcional; sem ele, comportamento legado).
            notification_context:  Dict com as variáveis do template do NotificationType.
                                   Ex.: {"streak_days": 14, "hours_remaining": 3}
        """
        # 1. Resolve Persona
        persona = PersonaService.get_persona_by_id(persona_id)
        if not persona:
            raise ValueError(f"Persona '{persona_id}' não encontrada.")

        persona_prompt = persona.system_prompt
        if persona_override and getattr(persona_override, "system_prompt", None):
            persona_prompt = persona_override.system_prompt

        # 2. Resolve NotificationType
        notif_type_block = ""
        effective_use_rag = use_rag  # pode ser None ainda

        if notification_type_id:
            notif_type = PersonaService.get_notification_type_by_id(notification_type_id)
            if not notif_type:
                raise ValueError(f"NotificationType '{notification_type_id}' não encontrado.")

            ctx = notification_context or {}

            # Valida variáveis obrigatórias
            missing = [v for v in notif_type.required_context_vars if v not in ctx]
            if missing:
                raise ValueError(
                    f"Variáveis obrigatórias ausentes para '{notification_type_id}': {missing}"
                )

            # Monta linha opcional de nome do usuário
            ctx.setdefault("user_first_name_line", "")
            if ctx.get("user_first_name"):
                ctx["user_first_name_line"] = f"Nome do usuário: {ctx['user_first_name']}\n"

            # Preenche variáveis opcionais com placeholder para não quebrar o .format_map
            filled_template = notif_type.system_prompt_template.format_map(
                _SafeDict(ctx)
            )
            notif_type_block = f"\n{filled_template}"

            # Decide use_rag: parâmetro explícito tem prioridade, senão usa default do tipo
            if effective_use_rag is None:
                effective_use_rag = notif_type.default_use_rag
        else:
            # Comportamento legado: sem tipo, RAG ativado por padrão
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
            f"{rag_context}\n"
            "Gere uma notificação curta (push notification) de 1 a 2 frases para o celular do usuário. "
            "Seja direto e mantenha sua personalidade intrínseca."
        )

        # 6. Chama o provider
        provider = get_llm_provider()
        try:
            message = await provider.generate(prompt, model_override=model_override)
            return message
        except Exception as e:
            logger.error(f"Erro ao gerar mensagem proativa para persona='{persona_id}': {e}")
            raise LLMProviderError(f"Falha na geração de mensagem: {e}")


# ---------------------------------------------------------------------------
# Utilitário interno
# ---------------------------------------------------------------------------

class _SafeDict(dict):
    """
    dict que retorna '{chave}' para chaves ausentes em str.format_map().
    Evita KeyError quando o template tem variáveis opcionais não fornecidas.
    """
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"