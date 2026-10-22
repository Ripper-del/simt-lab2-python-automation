# ЛР2. Автоматизація на Python

Утиліта `netmon.py`: інвентаризація і моніторинг проєкту ЛР1 по SSH двома способами (Docker CLI через Paramiko та Docker Engine API через SSH) з порівнянням результатів.

## Запуск (потрібна запущена ЛР1)
    ./setup.sh                                   # ключі SSH, known_hosts, venv, SSH-хост у контейнері
    .venv/bin/python netmon.py inventory         # inventory.json, report.csv
    .venv/bin/python netmon.py monitor --interval 5 --count 10   # monitoring.csv

Коди завершення: 0 успіх, 1 знайдено порушення чи розбіжності, 2 вузол недоступний або помилка автентифікації.

## Склад
- `netmon.py`, `requirements.txt`, `compose.yaml`, `ssh_host/` (контейнер, що імітує Linux VM із sshd).
- `evidence/`, `report/` (PDF, DOCX).
- Ключі створюються локально в `.state/` і не потрапляють у git.
- Перегенерація звіту: `pip install -r common/requirements-report.txt && LAB_AUTHOR="Прізвище_Ім'я" LAB_GROUP="ІО-XX" python build_report.py`
