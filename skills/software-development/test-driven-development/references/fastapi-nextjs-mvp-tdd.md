# FastAPI + Next.js MVP TDD Pattern

Use this reference when adding a small full-stack feature to a FastAPI backend plus Next.js App Router frontend.

## Backend RED/GREEN loop

1. Add focused FastAPI `TestClient` tests for the API contract first:
   - empty list
   - create payload → `201`
   - get by id
   - patch/update behavior
   - filter/query behavior
   - not-found behavior
2. Run only the new test file and verify it fails because the route/store function is missing, not because of a typo.
3. Implement the smallest in-memory model/store functions and router needed to pass.
4. Register the router in `app.main`.
5. Re-run the new test file, then the backend suite.

Typical commands:

```bash
uv run pytest tests/test_<feature>.py -q
uv run pytest -q
```

## Dashboard/API integration

When the feature contributes to a dashboard summary, add a separate failing dashboard test before editing the summary endpoint. Verify the failure is a missing field/key, then add the count/feature flag and rerun the dashboard tests.

## Frontend route loop

1. Add a Playwright smoke test for the new route before creating the page:

```ts
test('navigate to /feature page', async ({ page }) => {
  await page.goto('/feature')
  await expect(page.locator('h1')).toContainText('기능명')
})
```

2. Run the targeted Playwright test and verify it fails with `404`.
3. Create `src/app/<feature>/page.tsx` and wire the homepage card/link.
4. Re-run the targeted Playwright test.
5. Run `pnpm lint` and `pnpm build`.

Typical commands:

```bash
pnpm exec playwright test e2e/smoke.spec.ts --grep '<feature>'
pnpm lint
pnpm build
```

## Next.js App Router lint pitfalls

- Internal navigation should use `next/link` `Link`, not raw `<a href="/...">`.
- If a `useEffect` calls a local loader that depends on state, wrap the loader with `useCallback` and include it in the effect dependency array.
- If Playwright/Next dev repeatedly warns about an inferred workspace root and then cannot resolve dependencies such as `tailwindcss` from a parent folder, set `turbopack.root` in `next.config.ts` to the frontend directory (for example `turbopack: { root: __dirname }`) and restart any stale dev server on the test port.
- After adding a new page, run both lint and build; Playwright can pass while TypeScript or App Router lint still fails.

## What not to persist

Do not save one-off dependency/setup errors as rules. If direct `python -m pytest` misses project dependencies but `uv run pytest` works, the reusable lesson is to use the project runner documented by the project, not that the tool is broken.
