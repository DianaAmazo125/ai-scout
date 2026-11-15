# [Конспект от 10 ноября 2026 года, 17:05]
import httpx
import structlog
import os

logger = structlog.get_logger()

class AIService:
    def __init__(self):
        # По умолчанию используем DeepSeek — он дешёвый и стабильный в РФ
        self.api_url = "https://api.deepseek.com/chat/completions"
        self.api_key = "используй_свой_ключ"

    async def generate_proposal(self, job_text: str) -> str:
        """Генерирует продающий отклик на вакансию фриланса"""
        logger.info("отправка_запроса_в_нейросеть", text_len=len(job_text))
        
        system_prompt = (
            "Ты — опытный фрилансер, бэкенд-разработчик на Python и специалист по видеомонтажу (Reels/Shorts). "
            "Твоя задача — написать короткий, цепляющий и профессиональный отклик на вакансию. "
            "Пиши на русском языке, без лишней воды, сразу к делу. Сделай акцент на решении проблемы клиента. "
            "Не используй шаблонные фразы вроде 'Здравствуйте, я готов выполнить ваш заказ'."
        )
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "deepseek-chat",  # Быстрая и умная модель DeepSeek-V3
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Напиши отклик на эту вакансию:\n\n{job_text}"}
            ],
            "temperature": 0.7
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, json=data, headers=headers, timeout=30.0)
                
                if response.status_code == 200:
                    result = response.json()
                    proposal = result["choices"][0]["message"]["content"]
                    return proposal
                else:
                    logger.error("ошибка_api_нейросети", status=response.status_code, error=response.text)
                    return "⚠️ Не удалось сгенерировать отклик автоматически."
                    
        except Exception as e:
            logger.error("сбой_при_вызове_нейросети", error=str(e))
            return "⚠️ Ошибка подключения к ИИ-сервису."
