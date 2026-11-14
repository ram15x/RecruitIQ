# Notes on scoring and use

- The weights and credit values are my own choices, not learned from real hiring outcomes. Treat the score as a way to order a pile, not as a measure of how good a person is.
- The benchmark uses synthetic resumes written for five roles, so it measures how the scorer handles known shapes of resume. It does not measure hiring quality.
- The language-model helpers (skill suggestions, reviewer brief, question box, interview answer review) are tested against a mocked model only, so expect to tune the prompts. Free OpenRouter models may keep prompts, so for real candidates use a paid model or a no-retention provider.
- Dense similarity (`DenseSimilarity`) and Postgres are written but only tested on the defaults (TF-IDF and SQLite).
- Applying by email isn't a ticked consent box. Put a short notice in the job posting and check what your local rules require.
- Put the must-have and nice-to-have skills under separate headings in a job description, because that is how they are told apart.
- There is no hosted copy of the app. Render asks for a card on file even for free plans.
