#!/usr/bin/env bash
# Interactive walkthrough: each step waits for Enter. Needs ./scripts/run.sh running.
cd "$(dirname "$0")/.."
B=http://127.0.0.1:8000
api() { local body='{}'; [ -n "${2:-}" ] && body=$2; curl -s -X POST "$B/api/$1" -H 'content-type: application/json' -d "$body" >/dev/null; }
say() { printf "\n\033[1;96m%s\033[0m\n" "$1"; }
wait_enter() { printf "\033[2m%s\033[0m" "Нажмите Enter, чтобы продолжить..."; read -r; }

curl -s -m 3 "$B/api/snapshot" >/dev/null || { echo "Сначала запустите ./scripts/run.sh"; exit 1; }
clear
say "MIRAGE DEMO. Это окно = компьютер атакующего. Консоль банка открыта в Chrome."
say "ШАГ 1. Защита ВЫКЛЮЧЕНА. Атакующий подделал FaceID и выводит деньги через старый API."
echo "Смотрите в Chrome на баланс Ахмеда (AED 450,000): он будет падать до нуля."
wait_enter
api reset; api protection '{"on":false}'; sleep 2
.venv/bin/python attacker/attack.py --pace 0.7
say "Итог шага 1: деньги ушли по-настоящему. В Chrome красный баннер, реальный баланс Ахмеда = AED 0."
echo "Это и есть сценарий со слайда 9."
wait_enter

clear
say "ШАГ 2. Та же атака, но защита Mirage ВКЛЮЧЕНА."
echo "Смотрите в Chrome: реальный баланс Ахмеда останется 450,000, а справа будет то, что видит атакующий."
wait_enter
api reset; api protection '{"on":true}'; sleep 2
.venv/bin/python attacker/attack.py --pace 0.7
say "Атакующий уверен, что украл всё (см. выше: 9 раз APPROVED, баланс 0)."
echo "А в Chrome реальный баланс Ахмеда = AED 450,000. Атакующего тихо переключили в копию банка (фиолетовые MIRAGE в ленте)."
echo "Ниже в Chrome: почему сработало, куда он вёл деньги, ссылка на исправление от Devin."
wait_enter

say "ШАГ 3. Утро: подтверждаем мошенничество."
SID=$(curl -s "$B/api/snapshot" | .venv/bin/python -c "import json,sys; print(json.load(sys.stdin)['incident']['id'])")
api "incidents/$SID/fraud"
echo "В Chrome баннер 'FRAUD CONFIRMED': отложенные переводы отменены, счета мулов в отчёте."
say "Конец демо."
