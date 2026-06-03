# Weekly health report landscape verification notes

Session lesson:
- The user called out that the report had become too tall and wanted a more horizontal, report-like composition.
- Fix the layout in the HTML first, then render and inspect the PNG before delivering it.
- For this class of report, a wide canvas (about 2400px wide) worked better than a tall 1800px-wide card stack.
- Compress the lower narrative sections before trying to solve the issue by only increasing screenshot height.
- Verify the rendered PNG with a plain visual check; annotated browser screenshots are for internal inspection only.

Practical recipe:
1. Open the HTML locally in browser/headless mode.
2. Inspect the live layout and confirm no section is over-compressed.
3. Render a PNG in landscape.
4. Check for:
   - excessive vertical length,
   - cramped charts (especially calorie bars),
   - blank lower bands,
   - accidental debug/annotation overlays.
5. Iterate the HTML and re-render until the full report fits cleanly in one frame.
