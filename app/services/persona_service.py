"""
Serviço de Personas para mensagens proativas.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from app.services.llm_provider import get_llm_provider, LLMProviderError

logger = logging.getLogger(__name__)

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

# Configuração das 3 personas (tons) do Bot
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

# Configuração dos 3 perfis de usuários alvo
TARGET_PROFILES = [
    TargetProfile(
        id="gastao",
        name="O Gastão Sem Noção",
        description="Não economiza e não tem consciência.",
        context="O usuário desperdiça muita energia, deixa luzes acesas, banhos longos e não parece se importar com a conta ou o meio ambiente."
    ),
    TargetProfile(
        id="indiferente",
        name="O Indiferente",
        description="Ignora mensagens e não interage.",
        context="O usuário recebe várias notificações mas nunca abre o app. Ele ignora os avisos e continua com seus hábitos, tratando o bot como ruído."
    ),
    TargetProfile(
        id="engajado",
        name="O Engajado",
        description="Interage e busca economia.",
        context="O usuário já economiza, interage sempre com o app e busca novas formas de otimizar. Ele é um parceiro na missão de eficiência."
    )
]

class PersonaService:
    @staticmethod
    def get_personas() -> List[Persona]:
        return PERSONAS

    @staticmethod
    def get_persona_by_id(persona_id: str) -> Optional[Persona]:
        for persona in PERSONAS:
            if persona.id == persona_id:
                return persona
        return None

    @staticmethod
    def get_target_profiles() -> List[TargetProfile]:
        return TARGET_PROFILES

    @staticmethod
    def get_target_profile_by_id(profile_id: str) -> Optional[TargetProfile]:
        for profile in TARGET_PROFILES:
            if profile.id == profile_id:
                return profile
        return None

    @staticmethod
    async def generate_proactive_message(
        persona_id: str, 
        target_profile_id: Optional[str] = None,
        persona_override: Optional[object] = None, 
        model_override: Optional[str] = None
    ) -> str:
        """
        Gera uma mensagem proativa baseada na persona escolhida e no perfil do usuário alvo.
        
        Args:
            persona_id: ID da persona (tom do bot).
            target_profile_id: ID do perfil do usuário alvo (opcional).
            persona_override: Objeto com description e system_prompt opcionais.
            model_override: Nome do modelo para usar.
        """
        persona = PersonaService.get_persona_by_id(persona_id)
        if not persona:
            raise ValueError(f"Persona '{persona_id}' não encontrada.")
            
        target_context = ""
        if target_profile_id:
            target_profile = PersonaService.get_target_profile_by_id(target_profile_id)
            if target_profile:
                target_context = (
                    f"\nCONTEXTO DO USUÁRIO ALVO:\n"
                    f"Nome do Perfil: {target_profile.name}\n"
                    f"Descrição: {target_profile.context}\n"
                    "Adapte sua mensagem especificamente para este tipo de usuário, tentando engajá-lo da melhor forma possível dado o seu comportamento."
                )
        
        provider = get_llm_provider()
        
        # Define o system prompt base
        system_prompt = persona.system_prompt
        
        # Aplica o override se fornecido
        if persona_override:
            if getattr(persona_override, 'system_prompt', None):
                system_prompt = persona_override.system_prompt
        
        # Cria um prompt específico para gerar a mensagem inicial
        prompt = (
            f"Atue com a seguinte persona:\n{system_prompt}\n{target_context}\n\n"
            "Gere uma notificação curta (push notification) de 1 a 2 frases para o celular do usuário. "
            "Seja direto e mantenha sua personalidade intrínseca."
        )
        
        try:
            # Reutilizamos o método generate do provider com override de modelo se houver
            message = await provider.generate(prompt, model_override=model_override)
            return message
        except Exception as e:
            logger.error(f"Erro ao gerar mensagem proativa para {persona_id}: {e}")
            raise LLMProviderError(f"Falha na geração de mensagem: {e}")
