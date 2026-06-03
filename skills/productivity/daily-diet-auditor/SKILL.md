---
name: daily-diet-auditor
description: Use when the user tells you what they ate in a day and wants a concise judgment on the day's diet, nutritional gaps, and the next meal or adjustment. Summarize by time, total the day, and keep the tone neutral and practical.
version: 1.0.0
author: Miho Agent
license: MIT
metadata:
  miho:
    tags: [health, diet, nutrition, daily-log, korean, counseling]
    related_skills: [daily-health-image-card]
---

# Daily Diet Auditor

Use this skill when the user reports meals, snacks, drinks, supplements, or exercise and asks:

- how the day’s diet looks overall
- what seems 부족한지 / 과한지
- what to eat next
- whether the day’s flow is good
- how to summarize the day in a calm, practical Korean judgment

This skill is for **daily diet judgment**, not medical diagnosis or formal nutrition counseling.

## Core stance

- Read the user’s log in **time order**.
- Judge the day by **overall flow**, not one food item.
- Keep the tone **neutral, plain, and useful**.
- If the user’s thread uses time-based logging, preserve that time framing.
- Do **not** mix today’s food with yesterday’s or tomorrow’s food.
- If numbers are estimates, say so plainly: **대략 / 전후 / 추정**.

## When to use

- The user writes what they ate and asks “오늘 식단 어때?”
- The user asks what is missing in protein, carbs, vegetables, fiber, hydration, or meal balance.
- The user wants a next-meal suggestion based on what they already ate.
- The user wants a short Korean review, not a long lecture.
- The user asks for a custom diet judgment skill built around their recurring logs.

## What to check

Use this checklist in your head before answering:

1. **Time flow**
   - What did they eat first, second, last?
   - Was there a long gap that may have caused hunger rebound?
   - Did they bunch too much food into one late meal?

2. **Protein**
   - Was there a reliable protein source in the day?
   - Is protein spread across the day or all concentrated in one meal?

3. **Carbs**
   - Were carbs too sparse, too late, or too heavy?
   - Did carbs match the day’s activity level?

4. **Vegetables / fiber**
   - Any real vegetables, salad, seaweed, fruit, legumes, or other fiber source?
   - If missing, mention it gently.

5. **Fat / fried food / heavy sauces**
   - Any obvious overload?
   - If the day was already heavy, point to that softly.

6. **Hydration / salt**
   - If the user mentions salty food, soups, ramen, or sweating, note water and sodium balance.

7. **Calorie direction**
   - Do not invent exact calories unless the user gave enough to estimate.
   - If the day is clearly light, moderate, or heavy, say that.
   - If the user logs a branded chain food but the exact variant is unclear, give a **range** and mark it as **대략 / 전후 / 추정** instead of pretending precision.

8. **Context**
   - If the user trained, worked long hours, or had a special schedule, adapt the judgment.
   - A “light” day may be fine if activity was low; a “light” day may be too little if activity was high.

## Judgment model

Use this simple internal framing:

- **잘 맞음**: protein + carb + some fiber or vegetables + no big rebound gap
- **조금 아쉬움**: one major element is missing, but the day is still workable
- **보강 필요**: the day is too one-sided or too sparse
- **과함**: too much heavy food, too much late intake, or a clearly imbalanced flow

When possible, explain **why** in one sentence and then give the **next move**.

## Response structure

When answering the user, prefer this order:

1. **결론 한 줄**
   - “오늘 흐름은 괜찮다.”
   - “단백질은 괜찮고, 채소가 조금 부족하다.”
   - “저녁만 정리하면 전체 흐름이 깔끔해진다.”

2. **오늘 총칼로리 추정**
   - If the user gave food logs, always add a rough **total calories** line.
   - Mark it clearly as **대략 / 전후 / 추정** unless the user gave exact labels.
   - Keep the estimate honest and simple.

3. **무엇이 좋았는지**
   - one or two bullets

4. **무엇이 부족한지**
   - one or two bullets
   - be specific and calm

5. **다음 끼니 / 다음 행동**
   - one practical recommendation
   - keep it easy to follow

If the user wants a very short reply, compress to 2–3 lines.

## Preferred language style

- Use natural Korean.
- Prefer plain words like:
  - “단백질이 깔렸다”
  - “탄수가 너무 몰리지 않았다”
  - “채소/섬유질이 좀 비었다”
  - “저녁만 조금 정리하면 된다”
  - “흐름은 괜찮다”
- Avoid harsh or shaming language.
- Avoid dramatic phrasing like “망했다”.
- Avoid pretending to be exact when the data is partial.

## Example judgments

### Example 1: simple balanced day
- 아침에 닭가슴살, 점심에 밥, 저녁에 고기와 채소
- Judgment: “단백질과 탄수 밸런스는 괜찮고, 채소도 어느 정도 들어가서 흐름이 무난하다.”

### Example 2: protein-only until late
- 낮에 닭가슴살만 먹고 저녁에 고구마/밥을 조금
- Judgment: “단백질은 먼저 깔렸지만 채소와 식사 완성도가 조금 비었다. 저녁에 채소 한 번만 붙이면 더 깔끔하다.”

### Example 3: heavy late meal
- 낮에 거의 안 먹고 밤에 많이 먹음
- Judgment: “하루 총량보다도 몰아먹은 흐름이 아쉽다. 다음엔 낮에 가벼운 단백질을 먼저 넣는 게 낫다.”

## Common pitfalls

1. **오늘과 어제 식사를 섞는 것**
   - Never do that. Judge the current day only unless the user asks for a weekly view.

2. **한 끼만 보고 하루 전체를 단정하는 것**
   - One meal does not define the day.

3. **정확한 영양 수치를 허세처럼 말하는 것**
   - If you did not calculate it, keep it qualitative.

4. **너무 엄격하게 말하는 것**
   - The user wants a practical coach, not a scolding.

5. **애매한 시간대를 무시하는 것**
   - In this thread, time matters. Use the message time or the user’s stated time.

6. **의학적 진단처럼 말하는 것**
   - Do not diagnose. Keep it as diet guidance.

## Reference stack

Use these repositories as the default inspiration set when shaping judgments and language:

1. **`wger-project/wger`** — primary reference
   - Treat this as the strongest model for a practical diet/nutrition tracker.
   - It reinforces: food logging, calories, diet plans, weight tracking, and a usable food database.
   - When the user gives enough detail, you may estimate the day in terms of rough calorie direction and macro balance.
   - Prefer clear coaching language around: protein, carbs, vegetables/fiber, total intake, and meal timing.

2. **`simonoppowa/OpenNutriTracker`** — simplicity / privacy reference
   - Keep the review lightweight and understandable.
   - Avoid overcomplicated or over-precise nutrition talk when the input is sparse.
   - Favor short, direct judgments that the user can act on immediately.

3. **`maksimowiczm/FoodYou`** — privacy-first food diary reference
   - Respect partial logs and ambiguous meals.
   - If the data is incomplete, stay qualitative rather than pretending to have exact numbers.
   - Keep the tone calm and non-judgmental.

### Session notes

- See `references/2026-06-01-calorie-estimation-and-timing.md` for the session-specific calorie estimate pattern and timing rule that was derived from the user’s logs.
- See `references/2026-06-03-burgerking-wrap-calorie-lookup.md` for the chain-menu ambiguity pattern and range-based calorie lookup rule.

### How to apply the stack

- If the user gives a **full meal day**, use the **wger** lens: balance, calories, timing, protein spread, and missing fiber/vegetables.
- If the user gives only **rough snacks / one-off meals**, use the **OpenNutriTracker** lens: concise, simple, and not numerically fussy.
- If the user’s log is **private / incomplete / messy**, use the **FoodYou** lens: make the best judgment possible without overclaiming.
- When the user wants the next meal suggestion, tie it to what the day is missing rather than giving a generic healthy-food list.

## Optional customization hook

If the user later provides a GitHub repo, notes file, or a preferred nutrition framework, adapt the skill’s judgment language and thresholds to that source.

Examples of custom sources you might plug in later:

- a GitHub repo of diet rules or meal templates
- a markdown note with the user’s preferred diet constraints
- a weekly coaching rubric

## Verification checklist

- [ ] Meals were read in time order
- [ ] Today’s food was not mixed with another day
- [ ] The answer includes a clear overall judgment
- [ ] The answer includes a rough total calorie estimate when food logs are present
- [ ] The answer names at least one strength and one gap when relevant
- [ ] The next meal or next action is practical and specific
- [ ] Tone is neutral, concise, and human
- [ ] Any calorie estimate is clearly marked as an estimate
