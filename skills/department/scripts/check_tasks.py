#!/usr/bin/env python3
"""Перевірка плану тасків AI-департаменту.

Використання: python3 -I scripts/check_tasks.py projects/<slug>

Перевіряє docs/04-tasks.json проти брифу, специфікації, вимог безпеки й тест-плану:
  - кожна R, FR, AC, SEC покрита хоча б одним таском (NFR — лише попередження);
    R зі статусом «скасовано» чи «відкладено» в останній колонці маніфесту пропускаються;
  - документи на місці, ID у них знайдено, id тасків не дублюються;
  - хвилі узгоджені з полем wave, залежності існують, залежність завжди в ранішій
    хвилі, залежності від розрізаних (split) тасків немає;
  - зони файлів тасків однієї хвилі не перетинаються, два таски з міграціями
    не стоять в одній хвилі;
  - кожен таск має самодостатній файл (поле file) із розділами «Контекст» і
    «Критерії приймання»; його frontmatter (covers, files, deps) збігається з JSON;
    бюджет контексту порахований чесно, а L обґрунтовано;
  - кожен AC специфікації є в тест-плані docs/04-test-plan.md.
Таски зі статусом split у покриття не рахуються.
Код виходу 0 — план придатний, 1 — є помилки.
"""
import json
import re
import sys
from pathlib import Path

ID_PATTERNS = {
    "R": re.compile(r"^\|\s*(R-\d+)\s*\|.*$", re.M),
    "FR": re.compile(r"^###\s*(FR-\d+)", re.M),
    "AC": re.compile(r"\*\*(AC-\d+\.\d+[a-z]?)\*\*"),
    "NFR": re.compile(r"^\|\s*(NFR-\d+)\s*\|", re.M),
    "SEC": re.compile(r"^\|\s*(SEC-\d+)\s*\|", re.M),
}
EXCLUDED_STATUSES = ("скасовано", "відкладено")
KINDS = {"scaffold", "feature", "registration", "e2e", "bugfix"}
BUDGET_LIMITS = (("S", 40), ("M", 120))


def ids_from(path, kinds):
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    found = {}
    for kind in kinds:
        ids = set()
        for m in ID_PATTERNS[kind].finditer(text):
            if kind == "R":
                # Статус вимоги — лише в останній колонці маніфесту
                cells = [c.strip().lower() for c in m.group(0).strip().strip("|").split("|")]
                if cells and cells[-1] in EXCLUDED_STATUSES:
                    continue
            ids.add(m.group(1))
        found[kind] = ids
    return found


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith(" "):
            out[key.strip()] = value.strip()
    return out


def fm_list(value):
    """'["a", "b"]   # коментар' -> {'a', 'b'}; None, якщо не розібрати."""
    m = re.match(r"(\[.*?\])", value or "")
    if not m:
        return None
    try:
        return set(json.loads(m.group(1)))
    except json.JSONDecodeError:
        return None


def budget_lines(text):
    """Непорожні рядки від «## Навіщо» до кінця розділу «## Критерії приймання»."""
    lines = re.sub(r"<!--.*?-->", "", text, flags=re.S).splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("## Навіщо")), None)
    crit = next((i for i, l in enumerate(lines) if l.startswith("## Критерії приймання")), None)
    if start is None or crit is None:
        return None
    end = next((i for i in range(crit + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return sum(1 for l in lines[start + 1 : end] if l.strip() and not l.startswith("## "))


def budget_size(n):
    for size, limit in BUDGET_LIMITS:
        if n <= limit:
            return size
    return "L"


def zone_prefix(glob):
    """app/src/auth/** -> app/src/auth/ ; app/src/x.ts -> app/src/x.ts"""
    return re.split(r"[*?\[{]", glob, maxsplit=1)[0]


def zones_overlap(a, b):
    pa, pb = zone_prefix(a), zone_prefix(b)
    return pa.startswith(pb) or pb.startswith(pa)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    project = Path(sys.argv[1])
    docs = project / "docs"
    errors, warnings = [], []

    try:
        plan = json.loads((docs / "04-tasks.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ПОМИЛКА: немає {docs / '04-tasks.json'}")
        return 1
    except json.JSONDecodeError as e:
        print(f"ПОМИЛКА: 04-tasks.json не є валідним JSON: {e}")
        return 1

    tasks = {}
    for t in plan.get("tasks", []):
        if t.get("id") in tasks:
            errors.append(f"дублікат id таска: {t.get('id')}")
        tasks[t.get("id")] = t
    waves = plan.get("waves", [])
    active = {tid: t for tid, t in tasks.items() if t.get("status") != "split"}

    # Покриття
    for fn in ("01-brief.md", "03-spec.md", "03-security.md", "04-test-plan.md"):
        if not (docs / fn).exists():
            errors.append(f"немає {docs / fn}")
    required = {}
    required.update(ids_from(docs / "01-brief.md", ["R"]))
    required.update(ids_from(docs / "03-spec.md", ["FR", "AC", "NFR"]))
    required.update(ids_from(docs / "03-security.md", ["SEC"]))
    for kind, hint in (("R", "| R-NN |"), ("FR", "### FR-NN"), ("AC", "**AC-NN.N**")):
        if kind in required and not required[kind]:
            errors.append(f"не знайдено жодного {kind} — перевір формат ({hint})")
    covered = {c for t in active.values() for c in t.get("covers", [])}
    for kind, ids in required.items():
        missing = sorted(ids - covered)
        if missing:
            msg = f"{kind} без таска: {', '.join(missing)}"
            (warnings if kind == "NFR" else errors).append(msg)

    # Хвилі й залежності
    wave_of = {}
    for i, wave in enumerate(waves, start=1):
        for tid in wave:
            if tid not in tasks:
                errors.append(f"хвиля {i}: таска {tid} немає в списку tasks")
            elif tid in wave_of:
                errors.append(f"{tid} стоїть у кількох хвилях")
            else:
                wave_of[tid] = i
    for tid, t in tasks.items():
        if tid not in wave_of:
            errors.append(f"{tid} не входить у жодну хвилю")
            continue
        if t.get("wave") != wave_of[tid]:
            errors.append(f"{tid}: поле wave={t.get('wave')}, а стоїть у хвилі {wave_of[tid]}")
        if tid not in active:
            continue
        for dep in t.get("depends_on", []):
            if dep not in tasks:
                errors.append(f"{tid} залежить від неіснуючого {dep}")
            elif dep not in active:
                errors.append(f"{tid} залежить від розрізаного {dep} — переведи на нові таски")
            elif dep in wave_of and wave_of[dep] >= wave_of[tid]:
                errors.append(f"{tid} (хвиля {wave_of[tid]}) залежить від {dep} (хвиля {wave_of[dep]})")
        if not t.get("acceptance"):
            errors.append(f"{tid} без критеріїв приймання")
        if not t.get("files"):
            errors.append(f"{tid} без зони файлів")
        if t.get("kind") not in KINDS:
            warnings.append(f"{tid}: kind={t.get('kind')!r}, очікується одне з {sorted(KINDS)}")

    # Перетин зон і міграції в межах хвилі
    for i, wave in enumerate(waves, start=1):
        ids = [tid for tid in wave if tid in active]
        for a_i, a in enumerate(ids):
            for b in ids[a_i + 1 :]:
                for fa in active[a].get("files", []):
                    for fb in active[b].get("files", []):
                        if zones_overlap(fa, fb):
                            errors.append(f"хвиля {i}: {a} і {b} перетинаються ({fa} / {fb})")
        migrations = [tid for tid in ids if active[tid].get("migration")]
        if len(migrations) > 1:
            errors.append(f"хвиля {i}: кілька тасків із міграціями ({', '.join(migrations)})")

    # Самодостатні файли тасків
    budgets = {}
    for tid, t in active.items():
        rel = t.get("file")
        if not rel:
            errors.append(f"{tid} без поля file (шлях до файлу таска)")
            continue
        path = project / rel
        if not path.exists():
            errors.append(f"{tid}: файл таска {rel} не існує")
            continue
        text = path.read_text(encoding="utf-8")
        if "## Контекст" not in text or "## Критерії приймання" not in text:
            errors.append(f"{tid}: у {rel} бракує розділу «Контекст» чи «Критерії приймання»")
        fm = frontmatter(text)
        for fm_key, json_key in (("covers", "covers"), ("files", "files"), ("deps", "depends_on")):
            fm_val = fm_list(fm.get(fm_key))
            if fm_val is None:
                warnings.append(f"{tid}: у {rel} не вдалося прочитати {fm_key}")
            elif fm_val != set(t.get(json_key, [])):
                errors.append(f"{tid}: {fm_key} у {rel} не збігається з 04-tasks.json")
        declared = re.search(r'"?([SML])"?', fm.get("context_budget", ""))
        if not declared:
            warnings.append(f"{tid}: у {rel} немає context_budget")
            continue
        declared = declared.group(1)
        budgets[declared] = budgets.get(declared, 0) + 1
        counted = budget_lines(text)
        if counted is not None and "SML".index(budget_size(counted)) > "SML".index(declared):
            errors.append(f"{tid}: бюджет {declared}, а пораховано {counted} рядків ({budget_size(counted)})")
        if declared == "L" and "обґрунтовано" not in fm.get("context_budget", ""):
            errors.append(f"{tid}: бюджет контексту L без обґрунтування в {rel}")

    # Тест-план
    plan_path = docs / "04-test-plan.md"
    if plan_path.exists():
        in_plan = set(re.findall(r"AC-\d+\.\d+[a-z]?", plan_path.read_text(encoding="utf-8")))
        missing = sorted(required.get("AC", set()) - in_plan)
        if missing:
            errors.append(f"AC без рядка в тест-плані: {', '.join(missing)}")

    print(f"Тасків: {len(tasks)} (активних {len(active)}), хвиль: {len(waves)}")
    for kind, ids in required.items():
        print(f"  {kind}: {len(ids & covered)}/{len(ids)} покрито")
    if budgets:
        print("  бюджети контексту: " + ", ".join(f"{k}={v}" for k, v in sorted(budgets.items())))
    for w in warnings:
        print(f"ПОПЕРЕДЖЕННЯ: {w}")
    for e in errors:
        print(f"ПОМИЛКА: {e}")
    print("OK" if not errors else f"Помилок: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
