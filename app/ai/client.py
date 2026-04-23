import httpx
import asyncio
import os
from typing import Optional
from loguru import logger

# ── Konstanta ─────────────────────────────────────────────────
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

MAX_RETRIES = 3         # Maksimal retry per request
RETRY_DELAY = 2.0       # Detik antara retry (exponential backoff)
REQUEST_TIMEOUT =  60.0 # Timeout per request (detik)

class OpenRouterClient:
    """
    Async HTTP client untuk OpenRouter API.
    
    Fitur:
    - Retry otomatis dengan exponential backoff
    - Timeout handling
    - Error parsing yang informatif
    - Reuse HTTP connection (httpx.AsyncClient)
    """
    def __init__(self):
        self._client:Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy init client — buat hanya saat pertama kali dipakai."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=OPENROUTER_BASE_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    # Header ini disarankan OpenRouter untuk identifikasi app
                    "HTTP-Referer": "https://github.com/whatsapp-ai-bot",
                    "X-Title": "WhatsApp AI Bot",
                },
                timeout=httpx.Timeout(REQUEST_TIMEOUT),
            )
        return self._client
    
    async def close(self):
         """Tutup HTTP connection saat bot shutdown."""
         if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("OpenRouter client closed.")

    async def chat(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> Optional[str]:
        """
        Kirim request chat ke OpenRouter.

        Args:
            model_id  : ID model OpenRouter (contoh: "openai/gpt-oss-120b:free")
            messages  : List pesan dalam format OpenAI chat
                        [{"role": "user", "content": "..."}]
            max_tokens: Batas token output

        Returns:
            String respons dari model, atau None jika semua retry gagal.
        """
        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                client = await self._get_client()

                logger.debug(
                    f"[OpenRouter] Attempt {attempt}/{MAX_RETRIES} | "
                    f"Model: {model_id} | Messages: {len(messages)}"
                )

                response = await client.post("/chat/completions", json=payload)

                # ── Handle HTTP Error ──────────────────────────
                if response.status_code != 200:
                    error_body = response.text
                    logger.warning(
                        f"[OpenRouter] HTTP {response.status_code} | "
                        f"Model: {model_id} | Body: {error_body[:200]}"
                    )

                    # Rate limit — tunggu lebih lama
                    if response.status_code == 429:
                        wait = RETRY_DELAY * attempt * 2
                        logger.warning(f"[OpenRouter] Rate limited. Waiting {wait}s...")
                        await asyncio.sleep(wait)
                        continue

                    # Error 5xx (server error) — retry
                    if response.status_code >= 500:
                        await asyncio.sleep(RETRY_DELAY * attempt)
                        continue

                    # Error 4xx lain (auth, bad request) — jangan retry
                    return None


                # ── Parse Response ─────────────────────────────
                data = response.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )


                if not content:
                    logger.warning(f"[OpenRouter] Empty response from {model_id}")
                    return None
                
                logger.debug(
                    f"[OpenRouter] Success | Model: {model_id} | "
                    f"Token used: {data.get('usage', {}).get('total_tokens', '?')}"
                )
                return content

            except httpx.TimeoutException:
                logger.warning(
                    f"[OpenRouter] Timeout on attempt {attempt}/{MAX_RETRIES} | "
                    f"Model: {model_id}"
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * attempt)

            except httpx.RequestError as e:
                logger.warning(
                    f"[OpenRouter] Connection error on attempt {attempt}/{MAX_RETRIES} | "
                    f"Model: {model_id} | Error: {e}"
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * attempt)

            except Exception as e :
                logger.error(
                    f"[OpenRouter] Unexpected error | Model: {model_id} | {e}" 
                )
                return None
        
        logger.error(
            f"[OpenRouter] All {MAX_RETRIES} attempts failed | Model: {model_id}"
        )
        return None


# ── Singleton instance ─────────────────────────────────────────
# Satu client dipakai di seluruh aplikasi — efisien & hemat koneksi
openrouter_client = OpenRouterClient()