# Consultation note save flow

Session lesson:
- The `academy_consultation_note_save` wrapper can still ask for the student name even when the user message already contained it. Treat that as argument propagation failure, not as missing intent.
- Resolve the student explicitly with `AcademyStudentCardService.build(student_query, ...)` and then save to `ConsultationNoteRepository`.
- The local consultation note store lives at `~/.miho/academy_ops/consultation_notes.sqlite3` and is separate from PACA/Peak.

Minimal verified pattern:

```python
from plugins.academy_ops.auth_store import load_bindings, decrypt_token
from plugins.academy_ops.academy_api import AcademyApiClient
from plugins.academy_ops.student_card import AcademyStudentCardService
from plugins.academy_ops.consultation_notes import ConsultationNoteRepository

binding = next(iter(load_bindings().values()))
token = decrypt_token(binding.token_ciphertext) or ""
client = AcademyApiClient(token=token)
card = AcademyStudentCardService(client).build("백지민")
repo = ConsultationNoteRepository()
repo.add_note(
    discord_user_id=binding.discord_user_id,
    academy_id=binding.academy_id,
    paca_student_id=card.profile.paca_student_id,
    student_name=card.profile.name,
    note="목표 학교: 건국대",
)
```

Use this only for the local consultation-note DB; do not treat it as PACA/Peak write-back.
