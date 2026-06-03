# Vanilla JS + localStorage MVP TDD Pattern

Use this when the user asks for a small standalone browser app under `/Users/etlab/projects/<name>` and no backend/framework is necessary.

## Project placement

- If the user says “새 프로젝트” or “프로젝트 폴더 안에 <name>”, create `/Users/etlab/projects/<name>` as a standalone project.
- Check existence first; do not silently fold the feature into an existing neighboring project.
- Add a project-local `CLAUDE.md` describing the app.
- If `/Users/etlab/projects/CLAUDE.md` is being used as the registry, add a single row after the project exists.

## Minimal structure

```txt
<project>/
├── CLAUDE.md
├── README.md
├── index.html
├── package.json
├── src/
│   ├── app.js
│   ├── <domain>-store.js
│   └── styles.css
└── tests/
    └── <domain>-store.test.js
```

## TDD loop

1. Create `package.json` with `"type": "module"`, `"test": "node --test"`, and a simple static server script such as `"start": "python3 -m http.server 3720"`.
2. Write `node:test` unit tests first for pure domain functions:
   - create entry/object
   - filter by date/status
   - toggle/update behavior
   - summary/count behavior
3. Run `npm test` and verify RED failure from missing module/function.
4. Implement pure logic in `src/<domain>-store.js` until tests pass.
5. Build the browser shell with `index.html`, `src/app.js`, and `src/styles.css`.
6. Persist via `localStorage` helpers in the store module; keep DOM code thin and behavior-heavy code testable.
7. Verify:
   - `npm test`
   - start server with `npm start`
   - fetch or open the page and confirm a known heading appears.

## Pitfalls

- Do not spend time scaffolding Next/FastAPI if the user just wants a lightweight independent diary/tool.
- Browser UI code should call tested store functions rather than duplicating logic in event handlers.
- Use `textContent` for errors and escape rendered user content before assigning `innerHTML`.
