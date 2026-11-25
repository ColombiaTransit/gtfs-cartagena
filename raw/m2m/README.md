# M2M Control API snapshots

Data from the API behind the *Mi Bus Transcaribe* app (M2M Control, client
1343). See `docs/mibus-transcaribe-api.md`. Licensing is still to be asked
before the data goes into a published feed.

## valorTarifa.json

Fare shown in the app, fetched once on 2026-11-25 from
`https://m2m-web-teste.s3.us-east-1.amazonaws.com/cargas/1343/valorTarifa.json`.

- One field, `valor`: the general fare as display text, `"$ 3.900,00"` (COP).
- Matches the fare in force since 23 Jan 2026 (Decreto 017 de 2026).
- No tarifa diferencial (2.900 COP), no fare media, no transfer rules: those
  still come from the other sources (issue #29).
- The file lives in an S3 bucket named `m2m-web-teste` (test), so it may not be
  kept up to date; do not rely on it for fare changes.
