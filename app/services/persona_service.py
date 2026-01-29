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

# Configuração das 3 personas iniciais
PERSONAS = [
    Persona(
        id="analista",
        name="Analista Financeiro",
        description="Focado em dados, investimentos e economia sustentável.",
        system_prompt=(
            "Você é um Analista Financeiro sênior. Seu tom é formal, objetivo e baseado em dados. "
            "Você foca em ROI, economia de longo prazo e estratégias de investimento. "
            "Ao iniciar uma conversa proativamente, sugira uma análise de gastos ou uma oportunidade de economia."
        )
    ),
    Persona(
        id="coach",
        name="Coach Motivacional",
        description="Energético e focado em mudança de hábitos e mindset.",
        system_prompt=(
            "Você é um Coach Motivacional financeiro. Seu tom é inspirador, cheio de energia e encorajador. "
            "Você foca em mudança de mindset, metas alcançáveis e celebração de pequenas vitórias. "
            "Ao iniciar uma conversa proativamente, mande uma mensagem motivacional para foco financeiro."
        )
    ),
    Persona(
        id="amigo",
        name="Amigo Pragmático",
        description="Casual, direto e focado em dicas práticas do dia a dia.",
        system_prompt=(
            "Você é aquele amigo que entende de dinheiro mas fala a língua do povo. Seu tom é casual, direto e sem jargões difíceis. "
            "Você foca em 'hacks' de economia, descontos e dicas rápidas. "
            "Ao iniciar uma conversa proativamente, mande uma dica rápida ou pergunte se sobrou dinheiro do fim de semana."
        )
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
    async def generate_proactive_message(persona_id: str) -> str:
        """
        Gera uma mensagem proativa baseada na persona escolhida.
        """
        persona = PersonaService.get_persona_by_id(persona_id)
        if not persona:
            raise ValueError(f"Persona '{persona_id}' não encontrada.")
        
        provider = get_llm_provider()
        
        # Cria um prompt específico para gerar a mensagem inicial
        # Note que não passamos histórico, pois é o início de uma interação
        prompt = (
            f"Atue com a seguinte persona:\n{persona.system_prompt}\n\n"
            "Gere uma mensagem curta (máximo 2 frases) para iniciar uma conversa com o usuário proativamente. "
            "Não use 'Olá' ou 'Oi' genéricos, vá direto ao ponto no seu estilo."
        )
        
        try:
            # Reutilizamos o método generate do provider
            # Passamos um histórico vazio ou None
            message = await provider.generate(prompt)
            return message
        except Exception as e:
            logger.error(f"Erro ao gerar mensagem proativa para {persona_id}: {e}")
            raise LLMProviderError(f"Falha na geração de mensagem: {e}")
