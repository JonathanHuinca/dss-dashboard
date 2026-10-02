import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security_cipher import decrypt_api_key
from app.domain.config_models import ConfiguracionGlobal


class LLMClientBase(ABC):
    @abstractmethod
    def generate_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        response_mime_type: Optional[str] = None,
    ) -> Optional[str]:
        pass

    @abstractmethod
    def consult_intent(
        self,
        prompt: str,
        dataset_tipo: str,
        model_name: Optional[str] = None,
        grafico_contexto: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        pass


class GeminiClient(LLMClientBase):
    def __init__(self, api_key: str, default_model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.default_model = default_model
        try:
            from google import genai
        except ImportError:
            import sys
            sys.path.append(r"C:\Users\jonaw\AppData\Local\Programs\Python\Python310\lib\site-packages")
            from google import genai
        self.client = genai.Client(api_key=self.api_key)

    def generate_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        response_mime_type: Optional[str] = None,
    ) -> Optional[str]:
        chosen_model = model or self.default_model
        effective_model = (
            chosen_model
            if chosen_model in [
                "gemini-2.5-flash",
                "gemini-1.5-flash",
                "gemini-3.5-flash-lite",
                "gemini-3.1-flash-lite",
            ]
            else "gemini-2.5-flash"
        )
        config: Dict[str, Any] = {
            "temperature": temperature,
        }
        if system_instruction:
            config["system_instruction"] = system_instruction
        if response_mime_type:
            config["response_mime_type"] = response_mime_type

        res = self.client.models.generate_content(
            model=effective_model,
            contents=prompt,
            config=config,
        )
        return res.text if res else None

    def consult_intent(
        self,
        prompt: str,
        dataset_tipo: str,
        model_name: Optional[str] = None,
        grafico_contexto: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        context_directive = ""
        if grafico_contexto and grafico_contexto.strip():
            context_directive = (
                f"El usuario te está haciendo una pregunta específicamente sobre el gráfico de [{grafico_contexto.strip()}]. "
                "Basa tu análisis exclusivamente en estos datos. "
            )
        sys_prompt = (
            "Eres el Asistente Analítico DSS de la Universidad Católica de Temuco (Campus San Francisco). "
            f"{context_directive}"
            f"El usuario consulta sobre el recinto: {dataset_tipo}. "
            "Debes clasificar la intención analítica de la consulta del usuario. "
            "Intents disponibles: "
            "'monthly' (si pide gráfico o datos de un mes particular como marzo, abril, mayo, etc.), "
            "'weekly' (evolución por semanas o semanas de congestión), "
            "'exams' (impacto de certámenes, evaluaciones o hitos), "
            "'hourly' (franjas horarias, horas pico o valle), "
            "'cameras' (tráfico por cámara ANPR vehicular), "
            "'stay' (permanencia o perfiles de visita), "
            "'table' (si pide ver datos en formato tabla), "
            "'text' (consulta conceptual, informativa o de recomendación). "
            "Responde estrictamente con un objeto JSON válido con las llaves: "
            "\"tipo\" (\"plotly\" | \"df\" | \"text\"), "
            "\"intent\" (\"monthly\" | \"weekly\" | \"exams\" | \"hourly\" | \"cameras\" | \"stay\" | \"table\" | \"text\"), "
            "\"mes\" (entero del 1 al 12 o null si no aplica), "
            "\"explicacion\" (texto conciso y profesional respondiendo a la consulta basándote en los datos)."
        )
        try:
            raw_text = self.generate_response(
                prompt=prompt,
                system_instruction=sys_prompt,
                model=model_name or self.default_model,
                temperature=0.1,
                response_mime_type="application/json",
            )
            if not raw_text:
                return None
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned)
            return json.loads(cleaned)
        except Exception:
            return None


async def get_llm_client(db: AsyncSession = Depends(get_db)) -> LLMClientBase:
    stmt = select(ConfiguracionGlobal).where(ConfiguracionGlobal.id == 1)
    config = (await db.execute(stmt)).scalar_one_or_none()

    if not config or not config.encrypted_api_key or not config.encrypted_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falta configurar la IA: No se ha establecido una API Key en el panel de administración.",
        )

    try:
        decrypted_key = decrypt_api_key(config.encrypted_api_key)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falta configurar la IA: Error al descifrar la clave criptográfica. Verifique la variable FERNET_KEY.",
        )

    if not decrypted_key or not decrypted_key.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falta configurar la IA: La API Key configurada está vacía o es inválida.",
        )

    provider = (config.active_provider or "gemini").lower()
    default_model = config.default_model or "gemini-2.5-flash"

    if provider == "gemini":
        return GeminiClient(api_key=decrypted_key.strip(), default_model=default_model)
    else:
        return GeminiClient(api_key=decrypted_key.strip(), default_model=default_model)
