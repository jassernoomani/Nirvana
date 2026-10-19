import json
import logging
import os

from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime

load_dotenv()
logger = logging.getLogger(__name__)

client = OpenAI(
    base_url=os.getenv("AI_BASE_URL"),
    api_key=os.getenv("AI_API_KEY"),
)
MODEL = os.getenv("AI_MODEL", "openai/gpt-oss-20b")


def fallback_minutes(items, queue, staff):
    longest = max((i["prep_minutes"] for i in items), default=10)
    return round(longest + 1.5 * queue / max(staff, 1))


def estimate_prep_time(items, queue, staff, hour):
    prompt = f"""You estimate restaurant kitchen preparation time.
Order items (with base prep minutes): {items}
Orders currently in the kitchen: {queue}
Active kitchen staff: {staff}
Hour of day: {hour}

Reply ONLY with JSON: {{"minutes": <integer>, "reason": "<short sentence>"}}"""
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
            timeout=15,
        )
        data = json.loads(r.choices[0].message.content)
        minutes = int(data["minutes"])
        return {"minutes": max(5, min(minutes, 90)), "reason": data.get("reason", ""), "source": "ai"}
    except Exception as exc:
        logger.warning("AI estimate failed, using fallback: %s", exc)
        return {
            "minutes": fallback_minutes(items, queue, staff),
            "reason": "Standard estimate",
            "source": "fallback",
        }