# Розробка плагіна ai-department

Цей репозиторій — плагін Claude Code «AI-департамент» і водночас маркетплейс для нього. Опис для людини — у `README.md`.

## Що де лежить

- `agents/` — 16 агентів-ролей. У плагіні вони мають імена `ai-department:<агент>`.
- `skills/department/SKILL.md` — оркестратор `/department`.
- `skills/department/templates/`, `scripts/`, `dashboard/` — шаблони, перевірка плану й табло. В агентах і скілі на них посилаються через `${CLAUDE_PLUGIN_ROOT}/skills/department/...`.
- `.claude-plugin/plugin.json` і `marketplace.json` — опис плагіна і маркетплейсу.

## Правила змін

- Мова агентів, документів і спілкування — українська. Код, ідентифікатори й назви файлів — англійською.
- Перш ніж правити роль агента, прочитай `lessons.md` у робочій теці, де запускали проєкти, — там уроки з реальних прогонів.
- Змінив ID-формат у шаблоні (R-, FR-, AC-, SEC-) чи розділи файлу таска — онови `skills/department/scripts/check_tasks.py`.
- Змінив набір агентів чи етапів — онови `SKILL.md`, таблиці в `README.md` і ботів у `skills/department/dashboard/index.html`.
- Агентів плагіна `sdd` департамент напряму не викликає: потрібні правила перенесено в наших агентів.
- Перед кожним релізом: `claude plugin validate .`, підняти `version` у `.claude-plugin/plugin.json`, закомітити й запушити.
