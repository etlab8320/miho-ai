# MihoAI product intro reset from earlier source

Session lesson from a MihoAI promo infographic refinement.

## Trigger

The user explicitly pointed back to an earlier HTML file and said to organize from that file, while emphasizing the product name:

- Use the specified earlier source path as the working artifact, not the latest iteration.
- Rebuild the copy and visual hierarchy around the product name `미호AI`.
- Remove narrow owner/domain anchors when the goal is a generic product-introduction image.

## Durable workflow

1. Treat the user-specified source file as authoritative.
   - If they say `여기에서 정리해`, edit that exact file or create the next version from that file.
   - Do not continue patching a later file merely because it was the previous active artifact.
2. Make `미호AI` the first visual read.
   - Put it in the largest headline block.
   - Repeat it in the center/core node and section headings where natural.
3. Convert domain-specific copy to generic product language.
   - Remove visible terms like `맥스`, `체대입시`, `ET`, `학원`, `원장`, `학생`, `PACA`, `Peak`, `파카`, `피크` unless the user asks for that domain angle.
   - Replace with broader words: `사용자`, `업무`, `자료`, `결과물`, `반복 업무`, `전달`.
4. When the user says text was not actually enlarged, change real CSS font sizes, not just weight/padding.
5. Verify after rendering:
   - Run a text scan of the HTML/rendered DOM for removed domain anchors.
   - Check DOM overflow (`scrollHeight > clientHeight`) for cards/panels.
   - Inspect the full PNG visually for clipped lower rows and footer overlap.

## Copy direction that worked

- Hero: `미호AI — 말을 이해하고 결과까지 완성하는 AI`
- Support: `단순한 답변을 넘어, 필요한 정보를 찾고 정리하고 만들어 전달합니다.`
- Feature chips: `기억 / 정리 / 제작 / 전달`
- Core: `미호AI — 읽고 판단하고 실행해 결과물로 마무리합니다.`

## Pitfall

If a previous iteration added academy-specific anchors such as PACA/Peak, do not carry them forward into a generic product promo reset. The same image family may switch between domain-specific and generic product positioning depending on the latest instruction.