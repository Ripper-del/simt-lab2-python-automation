"""Формує звіт ЛР2 (PDF + DOCX) з файлів evidence/."""
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "common"))
from report_lib import Report

E = "evidence/"
AUTHOR = os.environ.get("LAB_AUTHOR", "Прізвище_Ім'я")
GROUP = os.environ.get("LAB_GROUP", "ІО-00")
r = Report(2, "Автоматизація мережевих задач. Інвентаризація та перевірка контейнерної мережі засобами Python через Docker CLI та Docker Engine API",
           AUTHOR, GROUP, "асистент кафедри ОТ Костянтин ГРІЩЕНКО", "report")


def fragment(name, start, end):
    """Витягує з netmon.py функцію від рядка start до рядка end."""
    s = open("netmon.py", encoding="utf-8").read()
    a = s.index(start)
    b = s.index(end, a) if end else len(s)
    return s[a:b].rstrip()


r.h1("1. Мета і завдання лабораторної роботи")
r.p("Мета: набути навичок автоматизованого збору мережевих даних засобами Python: обробка виводу Docker CLI через SSH (Paramiko) "
    "та робота зі структурованими даними Docker Engine API (Docker SDK for Python), перевірка доступності сервісів і формування звіту.")
r.p("Завдання (високий рівень): утиліта netmon.py збирає інвентаризацію проєкту ЛР1 двома способами, нормалізує дані, порівнює їх, "
    "перевіряє публікацію портів і роботу застосунку через проксі, зберігає inventory.json та report.csv; "
    "у режимі monitor періодично опитує стан контейнерів і HTTP та пише monitoring.csv.")

r.h1("2. Результати виконання")
r.h2("2.1. Версії та середовище")
r.step("Версії Python, бібліотек, Docker", "python --version; pip list; docker version; docker compose version", E + "01-versions.txt",
       "Python 3.13, paramiko 5.1.0, docker (SDK) 7.2.0, requests 2.34.2; Docker Engine 28.5.2, Compose v2.40.3.")
r.h2("2.2. Структура проєкту, встановлення і запуск")
r.bullets(["netmon.py — утиліта (режими inventory та monitor);",
           "requirements.txt — залежності з точними версіями;",
           "compose.yaml, ssh_host/ — контейнер lab2-sshhost, що імітує Linux VM з sshd та Docker CLI (вхід лише за ключем);",
           "setup.sh — генерація ключів, known_hosts, venv, запуск SSH-хоста;",
           "inventory.json, report.csv, monitoring.csv — результати."])
r.code("pip install -r requirements.txt\n./setup.sh\n.venv/bin/python netmon.py inventory\n.venv/bin/python netmon.py monitor --interval 10", "Команди встановлення і запуску")
r.p("Машиною керування є основна ОС (macOS), а роль Linux VM виконує контейнер lab2-sshhost (Alpine, sshd на 127.0.0.1:2222, "
    "доступ до Docker Engine через змонтований docker.sock). Паролі не використовуються; приватні ключі лежать у каталозі .state, який виключено з git. "
    "Ключ сервера перевіряється за локальним known_hosts (RejectPolicy, без автоматичного довіри).")

r.h2("2.3. Виконання пунктів завдання")
r.step("Пункт 1. SSH-доступ до Docker і сервісів ЛР1", "ssh lab@127.0.0.1 -p 2222 'hostname; docker info; docker compose ls'", E + "02-ssh-manual.txt",
       "Підключення за ключем працює, користувач бачить Docker Engine, а проєкт lab1 запущений (3 контейнери).")
r.step("Ручна перевірка застосунку", "curl http://127.0.0.1:8080/ (двічі)", E + "03-curl.txt",
       "Застосунок відповідає через проксі, лічильник у відповіді зростає — звернення до БД відбуваються.")
r.step("Пункти 2-6. Інвентаризація, перевірки, HTTP, порівняння", "python netmon.py inventory", E + "04-inventory.txt",
       "Через SSH+CLI та через Docker SDK отримано по 3 контейнери; таблиця «мережа → контейнери» показує app у двох мережах, "
       "перевірка портів видає «відповідає вимогам» (порт публікує лише proxy), два HTTP-запити дали 200 і лічильник +1 (proxy → app → db), "
       "порівняння CLI та API не виявило відмінностей.", 40)
r.step("Пункт 7. inventory.json", "head inventory.json", E + "05-inventory-json.txt",
       "Файл містить два знімки зі спільною структурою (cli та api): хост, проєкт, час збору та для кожного контейнера сервіс, повний ID, образ, стан, час запуску, мережі, IP та порти.", 30)
r.step("report.csv", "cat report.csv", E + "06-report-csv.txt",
       "Підсумкова таблиця містить результати всіх перевірок (мережі, порти, HTTP, порівняння CLI/API) у форматі CSV.", 30)

r.h2("2.4. Обробка помилок")
r.step("Недоступний вузол", "python netmon.py inventory --ssh-port 2299", E + "07-err-unreachable.txt",
       "Скрипт не падає з трасуванням, а повідомляє про недоступність вузла і завершується з кодом 2.")
r.step("Невірний ключ сервера", "python netmon.py inventory --known-hosts bad_known_hosts", E + "08-err-hostkey.txt",
       "Підключення відхилено: ключ сервера не збігається з відомим (захист від MITM).")
r.step("Помилка віддаленої команди", "run_ssh(ssh, 'docker inspect no-such-container')", E + "09-err-command.txt",
       "Ненульовий код завершення віддаленої команди перетворюється на помилку з текстом stderr.")
r.step("Порушення вимоги щодо портів", "docker run -p 9999:80 --label com.docker.compose.project=lab1 ...; python netmon.py inventory", E + "10-violation.txt",
       "Сторонній контейнер проєкту, що публікує порт 9999, виявлено: перевірка виводить назву контейнера і порти й завершується з кодом 1.", 40)

r.h2("2.5. Додаткове завдання: періодичний моніторинг")
r.step("Запуск моніторингу зі зупинкою та відновленням БД", "python netmon.py monitor --interval 3 --count 14 (паралельно docker stop db, через 12 с docker start db)", E + "11-monitor.txt",
       "Інтервал задається параметром --interval. Під час зупинки db стан показує db=exited, HTTP повертає 503, але моніторинг продовжується; після старту db HTTP знову 200.", 30)
r.step("Фрагмент monitoring.csv", "cat monitoring.csv", E + "12-monitoring-csv.txt",
       "Три етапи: норма (db=running, 200), збій (db=exited, 503), відновлення (db=running, 200). Затримка між зупинкою БД і появою 503 не перевищує інтервалу опитування.", 30)

r.h2("2.6. Ключові фрагменти коду")
r.code(fragment("n", "def collect_cli", "# ---------- збір через Docker Engine API"), "Збір через Docker CLI (Paramiko)")
r.code(fragment("n", "def collect_api", "# ---------- нормалізація"), "Збір через Docker Engine API (Docker SDK)")
r.code(fragment("n", "def normalize", "def snapshot"), "Нормалізація до спільної структури")
r.code(fragment("n", "def compare", "# ---------- перевірка мережевої"), "Порівняння CLI та API за повним ID")
r.code(fragment("n", "class StrictSSHAdapter", "# ---------- збір через Docker CLI"), "Docker SDK через SSH зі строгою перевіркою ключа")
r.p("Нормалізація приводить стани до нижнього регістру, час запуску до ISO-8601 UTC без наносекунд, мережі та порти до відсортованих списків рядків. "
    "Тому порядок елементів не впливає на порівняння. Повний код — у файлі netmon.py.")

r.h1("3. Висновки")
r.p("Створено Python-утиліту, що через SSH збирає інвентаризацію проєкту ЛР1 двома способами (текстовий вивід Docker CLI та структуровані дані Docker Engine API), "
    "зводить їх до спільної моделі й автоматично порівнює. CLI зручний для швидких одноразових команд, але потребує розбору тексту; API повертає структуровані "
    "дані й менш чутливий до формату виводу. Утиліта перевіряє мережеву конфігурацію, ланцюжок proxy → app → db та формує inventory.json і report.csv. "
    "Режим моніторингу показав, що збій БД видно за станом контейнера та HTTP-статусом 503, а відновлення фіксується наступним опитуванням.")
r.p("Підпис виконавця: ____________      Підпис викладача: ____________")
print(r.build())
