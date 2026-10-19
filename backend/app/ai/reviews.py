import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from app.ai import llm, prompts
from app.database import get_connection

Topic = Literal['slow_service', 'cold_food', 'food_quality', 'price', 'noise', 'wrong_order', 'staff', 'other']
Sentiment = Literal['positive', 'neutral', 'negative', 'mixed']
INJECTION = re.compile(r'ignore\s+(all\s+|any\s+|previous\s+|prior\s+)*(instructions|rules)|system\s+prompt|<\|system|reveal.*prompt|ignore.*previous', re.I)


class Complaint(BaseModel):
    model_config = ConfigDict(extra='forbid')
    topic: Topic
    quote: str = Field(min_length=2, max_length=240)


class ClassifiedReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: StrictInt
    sentiment: Sentiment
    complaints: list[Complaint] = Field(max_length=8)


class Batch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reviews: list[ClassifiedReview] = Field(max_length=8)


class Action(BaseModel):
    model_config = ConfigDict(extra='forbid')
    topic: Topic
    action: str = Field(min_length=1, max_length=300)


class Summary(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str = Field(min_length=1, max_length=900)
    actions: list[Action] = Field(max_length=3)


def redact(text, names=()):
    text = re.sub(r'\b[^\s@]+@[^\s@]+\.[^\s@]+\b', '[email removed]', text)
    text = re.sub(r'(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)', '[phone removed]', text)
    text = re.sub(r'https?://\S+', '[link removed]', text)
    for name in names:
        if len(name) >= 4:
            text = re.sub(re.escape(name), '[name removed]', text, flags=re.I)
    return text


def analyze(days=30, limit=24):
    now = datetime.now()
    cutoff = (now - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    end = now.strftime('%Y-%m-%d %H:%M:%S')
    with get_connection() as c:
        stats = c.execute('SELECT count(*) n,avg(rating) avg FROM reviews WHERE created_at>=? AND created_at<=?', (cutoff, end)).fetchone()
        rows = c.execute("SELECT id,rating,comment,created_at FROM reviews WHERE created_at>=? AND created_at<=? AND trim(coalesce(comment,''))!='' ORDER BY created_at DESC,id DESC LIMIT ?", (cutoff, end, limit)).fetchall()
        names = [r[0] for r in c.execute('SELECT full_name FROM users')]
    entries, flagged = [], 0
    for row in rows:
        if INJECTION.search(row['comment']):
            flagged += 1
            continue
        text = redact(row['comment'], names)[:1400]
        entries.append({'id': row['id'], 'text': text, 'rating': row['rating'], 'created_at': row['created_at']})
    analyzed, pending, failures = [], [], []
    model_key = llm.settings()['model'] + ':' + prompts.PROMPT_VERSION
    for entry in entries:
        digest = hashlib.sha256(entry['text'].encode()).hexdigest()
        with get_connection() as c:
            cached = c.execute('SELECT payload FROM ai_review_analysis WHERE review_id=? AND content_hash=? AND model_key=?', (entry['id'], digest, model_key)).fetchone()
        if cached:
            try:
                classification = ClassifiedReview.model_validate_json(cached['payload'])
                analyzed.append((entry, classification))
                continue
            except ValueError:
                pass
        pending.append((entry, digest))
    # Small local models are more reliable when reviews cannot contaminate each other.
    for offset in range(0, len(pending)):
        chunk = pending[offset:offset + 1]
        data = {entry['id']: (entry, digest) for entry, digest in chunk}
        try:
            result = llm.generate(prompts.REVIEW_CLASSIFICATION, {'reviews': [{'id': e['id'], 'text': e['text']} for e, _ in chunk]}, Batch)
            if len(result.reviews) != len(data) or {r.id for r in result.reviews} != set(data):
                raise llm.LocalModelError('Review IDs did not match the requested sample.')
            for review in result.reviews:
                entry, digest = data[review.id]
                if any(complaint.quote.casefold() not in entry['text'].casefold() for complaint in review.complaints):
                    raise llm.LocalModelError('The model returned a complaint without a matching evidence quote.')
                if any(complaint.topic == 'cold_food' and not re.search(r'cold|cool|lukewarm|room.temperature|not (?:hot|warm)|froid|ti[eè]de|pas chaud', complaint.quote, re.I) for complaint in review.complaints):
                    raise llm.LocalModelError('A cold-food complaint did not contain temperature evidence. The result was not counted.')
                if review.sentiment == 'positive' and review.complaints:
                    raise llm.LocalModelError('A review classification contradicted its complaint evidence. The result was not counted.')
            with get_connection() as c:
                for review in result.reviews:
                    entry, digest = data[review.id]
                    c.execute('INSERT OR REPLACE INTO ai_review_analysis (review_id,content_hash,model_key,payload) VALUES (?,?,?,?)', (review.id, digest, model_key, review.model_dump_json()))
                    analyzed.append((entry, review))
        except llm.LocalModelError as exc:
            failures.append(str(exc))
            break
    sentiments = Counter(r.sentiment for _, r in analyzed)
    topics = Counter(topic for _, review in analyzed for topic in {c.topic for c in review.complaints})
    examples = []
    for entry, review in sorted(analyzed, key=lambda item: item[0]['created_at'], reverse=True):
        examples.append({'id': entry['id'], 'date': entry['created_at'], 'rating': entry['rating'], 'text': entry['text'], **review.model_dump(exclude={'id'})})
    summary = None
    if analyzed:
        try:
            result = llm.generate(prompts.REVIEW_SUMMARY, {'analyzed_sample': len(analyzed), 'sentiments': dict(sentiments), 'complaints': dict(topics)}, Summary)
            if any(action.topic not in topics for action in result.actions):
                raise llm.LocalModelError('Summary actions referenced a topic absent from the analyzed sample.')
            summary = {'summary': redact(result.summary, names), 'actions': [{'topic': a.topic, 'action': redact(a.action, names)} for a in result.actions]}
        except llm.LocalModelError as exc:
            failures.append(str(exc))
    return {'days': days, 'total_reviews': stats['n'], 'average_rating': round(stats['avg'], 2) if stats['avg'] is not None else None,
            'sample_size': len(rows), 'analyzed_count': len(analyzed), 'pending_count': len(entries) - len(analyzed),
            'flagged_count': flagged, 'sentiments': dict(sentiments),
            'topics': [{'topic': topic, 'count': count, 'review_ids': [review.id for _, review in analyzed if any(c.topic == topic for c in review.complaints)]} for topic, count in topics.most_common()],
            'examples': examples, 'insights': summary, 'model': llm.settings()['model'], 'warnings': failures,
            'notice': 'Most recent non-empty reviews in the selected period, bounded by the sample limit. Contact details and known full names are redacted; suspicious instruction text is excluded. Counts describe analyzed reviews only. Interpret model suggestions with human review.'}
