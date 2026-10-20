"""Export the exact runtime system prompts for review or a teacher presentation."""
from pathlib import Path
from app.ai import prompts

sections = [('Recommendation reranking', prompts.RECOMMENDATIONS),
            ('Review complaint and praise extraction (the sentiment is derived from these quotes in code)', prompts.REVIEW_CLASSIFICATION),
            ('Manager briefing', prompts.REVIEW_SUMMARY),
            ('Kitchen preparation-time estimate', prompts.PREP_TIME)]
text = '# Exact local AI prompts\n\nVersion: ' + prompts.PROMPT_VERSION + '\n\n'
text += 'Forecasting uses scikit-learn and has no LLM prompt. The following system prompts are paired with separate JSON data messages.\n\n'
for title, prompt in sections:
    text += f'## {title}\n\n```text\n{prompt}\n```\n\n'
target = Path(__file__).resolve().parent.parent / 'AI_PROMPTS.md'
target.write_text(text, encoding='utf-8')
print(target)
