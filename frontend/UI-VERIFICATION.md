# Recall.cs interface verification

## Product direction

Recall.cs is a study and reading space within the portfolio's shared visual family. The shell uses navy, warm white, restrained ice blue, fine borders, and small radii. The primary study surfaces use warm paper with muted green annotations, Satoshi interface labels, Source Serif 4 for questions/reference reading, and JetBrains Mono metadata.

The new landing page uses a clearly labeled illustrative teaching card with a working reference disclosure. It contains no invented session score, retention result, or schedule. The actual protected review flow uses the same extracted `ReviewWorkspace` as the design fixture: question first, explanation composer, then reference/feedback in a margin column. The backend still decides when source context is available.

The dashboard, learning-path, setup, tutor, and summary retain their existing screen layouts while inheriting the shared shell/tokens. They have not all been individually redesigned.

## Behavior corrections

- Explicit verdict normalization prevents `incorrect` from matching the `correct` suffix. Missing/failed/unknown grading remains ungraded.
- A submission error leaves the current explanation and form visible so the user can retry.
- Submission and skip handlers reject duplicate actions while a request is active or feedback is already present.
- Progress starts at zero before the first response rather than counting the currently displayed card as completed.
- Missing, invalid, or ungraded model scores show unavailable, not a zero score bar.
- Feedback exposes the supplied source chunk ID when available, and avoids inventing missed concepts when the response omits them.

## Credential-free preview

Run `pnpm dev --host 127.0.0.1 --port 4184 --strictPort`, then open `http://127.0.0.1:4184/design-preview.html`.

The separate development entry imports the real `StudyFrame`, `LandingReadingView`, `ReviewWorkspace`, `ReviewNotes`, and `FeedbackPanel`. It mounts no Clerk provider, session controller, or backend data hook. A deny-all fetch adapter rejects accidental network calls. All sample records/feedback are explicitly labeled synthetic in the banner.

Click Practice or Study desk to inspect the fixture review. The banner switches question, feedback, incorrect, don't-know, grading-error, missing-source, loading, error, empty, and long-text states. Typing, checking, skipping, reference disclosure, and continuing operate on local fixture state only. No record is saved.

The HTML is not a production Vite input. Its source is not imported by `main.tsx` and its mount is also guarded by `import.meta.env.DEV`. Production output contains no fixture HTML or records. This checks rendering/local interaction, not authenticated grading or live retrieval.

## Local validation

- `pnpm build`
- `pnpm lint`
- `node --test tests/verdict.test.mjs` (5 regression tests; Node with native TypeScript stripping)

The local frontend has no configured `VITE_CLERK_PUBLISHABLE_KEY`. Its existing application entry throws when that value is absent, and Vite can eliminate the unreachable application branch in that build. A successful build therefore confirms TypeScript/bundler acceptance, not a runnable authenticated production deployment. No placeholder credentials were inserted. The isolated preview verifies actual presentation components independently of this missing configuration.

Preexisting dependency junctions referenced the old repository location. The old tree is preserved in ignored `.deps-before-ui-20261025/`; a frozen-lockfile installation restored the exact existing versions. The pnpm 11 workspace explicitly denies the Clerk shared package's postinstall telemetry-notice script; no SDK version upgrade or postinstall execution was needed.
