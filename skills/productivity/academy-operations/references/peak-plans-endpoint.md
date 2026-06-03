# Peak plans endpoint notes

Session context: Discord academy-operations request for “어제 박성준 운동계획서”.

## Verified read path

Use the stored PACA/Peak bearer token and call:

```http
GET /peak/plans?date=YYYY-MM-DD
Authorization: Bearer <token>
```

Observed base URL in the local plugin flow was `DEFAULT_PACA_BASE_URL` / `MIHO_ACADEMY_PACA_BASE_URL`.

## Observed response shape

Top-level fields:

- `success`: boolean
- `date`: requested/served date
- `slots`: scheduled instructors by `morning`, `afternoon`, `evening`
- `plans`: list of daily plans
- `stats`: sometimes present when no plans are returned

Each `plans[]` row may include:

- `id`, `academy_id`, `date`, `time_slot`
- `trainer_id`, `instructor_id`, `instructor_name`, `isOwner`
- `description`, `tags`
- `exercises`: list of `{id, exercise_id, name, note, reps, weight}`
- `completed_exercises`: list of completed exercise IDs
- `extra_exercises`
- `exercise_times`: map of exercise ID to completion timestamp
- `created_at`, `updated_at`

## Important quirk

`GET /peak/plans?date=YYYY-MM-DD&instructor=박성준` returned the same full plan list as `date` alone. Do not trust that parameter as a server-side filter. Fetch by date and filter locally by `instructor_name` or `instructor_id`.

Wrong date parameter names such as `target_date`, `start_date`, or `end_date` caused the endpoint to serve the current date rather than the requested past date in the observed session. Use `date`.

## User-facing format

For a named instructor, return a compact Korean plan:

- date, time slot, instructor, plan ID, updated time
- description if present
- numbered exercises
- include notes under the exercise when present
- mark completion based on `completed_exercises`

Avoid dumping raw JSON or exposing tokens/IDs beyond operationally useful fields like plan ID.
