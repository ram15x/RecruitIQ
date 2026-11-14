# Architecture

```
resume file / webhook / form
        |
  text extraction (PDF, DOCX, TXT by content, not by extension)
        |
  consent check  ->  stored with a retention date
        |
  PII masking (names, contact lines, personal details, pronouns)
        |
  +-- skills (ontology match, evidenced vs listed vs related)
  +-- experience (merged date ranges)
  +-- similarity (TF-IDF, or dense if plugged in)
  +-- injection scan (flags only)
        |
  weighted score + evidence + flags + notes   (stored as JSON on the application)
        |
  blind ranked list  ->  person reads evidence  ->  decision with a required reason
        |
  draft email (sent only on a button press)   /   interview link (signed, windowed, one use)
```

## Decisions and why

**Rules and an ontology instead of a language model for the score.** Every number can be traced to a skill and a line of text, the same input always gives the same output, and a resume cannot talk the scorer into anything. The cost is that it misses meaning when the words are different.

**Masking before scoring, with no placeholder tokens.** Names are not replaced with a placeholder token such as `[candidate]`, because the token itself leaks into the similarity part and moves scores. The masked text is only used for scoring and the removed text is simply deleted. That is why the invariance test shows a change of exactly 0.

**The injection scanner only flags.** If a flag subtracted points, anyone could push a rival down by pasting suspicious text into their own resume. A flag asks for a closer look and nothing else.

**Reciprocal rank fusion is only for ordering a pool.** It gives a rank, not an absolute score, and fusing a list of one item gives a constant. It is in `similarity.py` for combining several rankings and is not used to produce the score shown to a person.

**Blind list, audited reveal.** The list API never returns names. The detail endpoint returns identity only with `reveal=true`, and each reveal is logged.

**Organisation scoping in every query.** Each table that holds tenant data carries an `org_id`, and every route filters on the signed-in user's organisation. A test tries each route from a second organisation.

**Interview links are JWTs with an id.** The token carries the interview id, a unique id that must match the stored one, and an expiry set to the end of the window. The server also checks the schedule, the grace period and the status, so a link cannot be reused after submission.

## Data

SQLite by default, any SQLAlchemy URL otherwise. Tables: organisations, users, jobs, candidates, applications, interviews, demographics (kept apart from candidates and never read by the scorer), notifications, audit log.
