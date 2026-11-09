# TraceGuard Eval

Projekt Przejściowy. Specyfikacja projektu

| Parametr | Ustalenie |
| --- | --- |
| Wykonawca | ................................................................................ |
| Kontekst | WIT / PWr, Informatyczne Systemy Automatyki, specjalność Zastosowania Technologii Informacyjnych |
| Kurs | Projekt Przejściowy (PP): W04ISA-SM0209P |
| Tryb | Realizacja indywidualna |
| Zakres | Ewaluator offline, kontrolowany symulator, jedna konfiguracja agenta, jeden model oceniający, kalibracja, raport i demonstrator aplikacyjny |
| Technologie | Python, FastAPI, PostgreSQL i pakiet domenowy `traceguard_core`. Gotowy LLM przez API, bez lokalnego treningu w zakresie podstawowym |

## 1. Definicja problemu

Agenci wykorzystujący duże modele językowe (LLM) wykonują zadania przez wywoływanie narzędzi. Poprawnie brzmiąca odpowiedź końcowa nie gwarantuje poprawnego przebiegu. Agent może użyć błędnych argumentów, pominąć weryfikację efektu lub wykonać operację bez wymaganych uprawnień. Sama ocena odpowiedzi końcowej może nie ujawnić takich błędów.

Celem projektu jest stworzenie aplikacji do wielokryterialnej oceny trajektorii agenta, czyli uporządkowanego zapisu zadania, wywołań narzędzi, ich argumentów i wyników oraz odpowiedzi końcowej. Przypadkiem zastosowania jest obsługa incydentów usługowych w lokalnym, kontrolowanym symulatorze.

Aplikacja importuje i waliduje trajektorie, zapisuje dane i oceny oraz wskazuje dowody dla wykrytych uchybień. Ocena obejmuje pięć kryteriów.

| Kryterium | Zakres |
| --- | --- |
| Wykonanie zadania | Osiągnięcie wymaganego stanu końcowego |
| Dobór narzędzi i weryfikacja | Dopuszczalność narzędzi, spełnienie warunków ich użycia i sprawdzenie efektów działań |
| Argumenty | Poprawność typów, wartości i zasobu docelowego |
| Ograniczenia i uprawnienia | Brak zabronionych operacji, naruszeń uprawnień i zmian poza zakresem |
| Zgodność odpowiedzi | Zgodność twierdzeń agenta z obserwacjami |

Reguły deterministyczne sprawdzają stan i przebieg operacji. Gotowy LLM przez API ocenia obserwowalną trajektorię bez dostępu do etykiet referencyjnych. Referencje wynikają z testów, jawnych reguł i niezależnej kontroli człowieka. Ocena LLM nie stanowi automatycznie prawdy odniesienia.

Porównanie obejmuje ocenę globalną `PASS` lub `FAIL`, ocenę wielokryterialną, skalę 1-10 oraz wybór A, B albo remisu w porównaniach parami. Wszystkie formaty korzystają z tego samego modelu, kryteriów i danych wejściowych. Osobny warunek porównuje dostęp do pełnej trajektorii z dostępem wyłącznie do odpowiedzi końcowej.

Rdzeń oceny działa niezależnie od interfejsu HTTP i bazy danych. CLI, analiza offline i aplikacja używają tych samych schematów, rubryk, parserów i konfiguracji. Zbiór i podział na kalibrację oraz test są wspólne dla wszystkich sposobów uruchomienia.

## 2. Stack technologiczny

| Warstwa | Technologie | Zastosowanie |
| --- | --- | --- |
| Rdzeń i walidacja | Python, Pydantic 2, `traceguard_core` | Modele trajektorii, rubryk i wyników, reguły oceny oraz walidacja importu JSONL |
| Symulator | `traceguard_sim` | Deterministyczny stan usług, narzędzia, kontrolowane mutacje i odtwarzanie przebiegów |
| Backend | FastAPI, Uvicorn | REST API i usługi aplikacji. Logika oceny niezależna od warstwy HTTP |
| Baza i migracje | PostgreSQL, SQLAlchemy 2, psycopg 3, Alembic | Trwały zapis trajektorii, konfiguracji i ocen, zdarzenia w JSONB, migracje schematu |
| Integracja LLM | HTTPX, adapter dostawcy API | Wywołania modelu, timeouty, walidacja odpowiedzi, rejestr błędów i zużycia tokenów |
| Interfejs | Jinja2, HTML, CSS | Lista trajektorii, filtry, szczegóły ocen, porównania parami i powiązane dowody |
| Analiza i raporty | pandas, NumPy, scikit-learn, Matplotlib | Metryki jakości i stabilności, wykresy, eksport CSV i JSON oraz raport HTML |
| Uruchamianie badań | CLI, Jupyter | Kalibracja, zamrażanie konfiguracji, powtórzenia i analiza bez serwera ani bazy |
| Testy | pytest, unittest.mock, respx, testcontainers | Testy symulatora, reguł, adaptera API, trwałego zapisu oraz wznawiania zadań |
| Środowisko | uv, `pyproject.toml`, `uv.lock`, Git, Docker Compose | Przypięte zależności, kontrola wersji i lokalne uruchomienie aplikacji z bazą |

Rdzeń nie importuje FastAPI ani SQLAlchemy. Adaptery zapisu obsługują pliki lub bazę danych bez kopiowania logiki domenowej.

## 3. Kryteria sukcesu

### K1. Działający import i trwały zapis

Poprawne pliki JSONL są walidowane i zapisywane w PostgreSQL. Niepoprawne dane są odrzucane z czytelnym komunikatem. Dla każdej oceny można ustalić trajektorię, model, konfigurację, wersję rubryki i promptu. Trajektorie i wyniki mają wersje schematów oraz hashe treści.

### K2. Kontrolowany zbiór demonstracyjny

Zbiór docelowy zawiera 150 trajektorii: 30 scenariuszy bazowych z pięciu rodzin incydentów, po 2 poprawne realizacje i 3 warianty z błędem. Katalog scenariuszy określa przynależność do rodzin. Mutacje są ponownie wykonywane w symulatorze, aby stan, odpowiedzi narzędzi i zapis pozostały spójne. Inna poprawna kolejność działań nie jest automatycznie błędem.

| Część zbioru | Scenariusze | Trajektorie | Zastosowanie |
| --- | --- | --- | --- |
| Pilot i kalibracja | 20 | 100 | Dobór promptów, parametrów i progu punktowego |
| Test | 10 | 50 | Końcowe porównanie zamrożonych metod |
| Razem | 30 | 150 | Po 2 poprawne i 3 błędne przebiegi na scenariusz |

Warianty tego samego scenariusza i scenariusze o tym samym szablonie pozostają w jednej części. Przydział grup zostaje ustalony przed strojeniem. Podział uwzględnia rodziny incydentów, a różnice ich rozkładu są opisane w raporcie. Strojenie na odpowiednikach zamrożonych grup testowych jest blokowane również w innych profilach i uruchomieniach.

Etykiety wynikają ze stanu symulatora i jawnych warunków poprawności oraz są sprawdzane ręcznie dla wszystkich 150 trajektorii. Plan obejmuje niezależną ocenę 20 trajektorii testowych przez drugiego annotatora i rozstrzygnięcie sporów przed testem końcowym. Brak drugiej osoby jest opisany jako ograniczenie, bez deklarowania zgodności między annotatorami.

Zmniejszony zbiór jest jawnie oznaczony jako pilot, a nie realizacja pełnego zakresu K2.

### K3. Wielokryterialna ocena z dowodami

Reguły kontrolne i LLM oceniają trajektorie według pięciu kryteriów z sekcji 1. Wynik zawiera ocenę, uzasadnienie i identyfikator zdarzenia lub cytat stanowiący dowód. System rozróżnia `PASS`, `FAIL`, brak zastosowania `NA`, brak wystarczających dowodów `INDETERMINATE` oraz techniczny status `ERROR` ewaluatora.

Wynik łączny `PASS` wymaga `PASS` wszystkich adekwatnych kryteriów. `FAIL` dowolnego kryterium daje `FAIL` całości. Jeżeli nie ma `FAIL`, ale co najmniej jedno adekwatne kryterium pozostaje nierozstrzygnięte, wynik jest `INDETERMINATE`. Sam zestaw `NA` również nie uprawnia do `PASS`.

Etykiety referencyjne i informacje o mutacji nie trafiają do danych przekazywanych LLM. Brak dowodów ani błąd techniczny nie są automatycznie uznawane za błąd agenta.

### K4. Jawna i przetestowana decyzja jakościowa

Decyzja aplikacyjna jest odrębna od wyniku oceny trajektorii. Obowiązuje następująca kolejność reguł.

1. Wykryte naruszenie krytyczne, w tym naruszenie uprawnień, daje `BLOCK` niezależnie od pozostałych ocen.
2. Brak rozstrzygnięcia, brak wymaganej oceny lub błąd techniczny daje `REVIEW`, o ile nie wykryto naruszenia krytycznego.
3. Komplet `PASS` dla wymaganych, adekwatnych kryteriów daje `ACCEPT`. `NA` wymaga uzasadnienia, a sam zestaw `NA` daje `REVIEW`.
4. Pozostałe rozstrzygnięte przypadki dają `BLOCK`.

Zestaw testowy obejmuje wszystkie decyzje i statusy oraz ich pierwszeństwo. Wszystkie przypadki przechodzą testy. Przywrócenie usługi nie kompensuje naruszenia ograniczeń, na przykład usunięcia chronionych logów.

### K5. Porównanie metod i raport wyników

Ocena globalna, wielokryterialna i punktowa w skali 1-10 są porównane na części testowej po zamrożeniu konfiguracji. Próg punktowy jest dobrany wyłącznie na pilotażu. Każdy format jest uruchamiany trzykrotnie, bez współdzielenia odpowiedzi z cache między powtórzeniami.

Porównania parami obejmują 20 zamrożonych par trajektorii tych samych zadań. Lista zawiera porównania poprawnego przebiegu z błędnym oraz dwóch poprawnych realizacji z możliwym remisem. Każda para jest oceniana w obu kolejnościach A/B w każdym z trzech powtórzeń.

Osobna analiza porównuje pełną trajektorię z samą odpowiedzią końcową, bez mieszania wpływu ilości dowodów z wpływem formatu oceny.

Raport zawiera macierze pomyłek, precision, recall i F1 dla klasy `FAIL`, accuracy, wyniki poszczególnych kryteriów, fałszywe alarmy, przeoczenia krytyczne, pokrycie ocen, stabilność powtórzeń oraz czas i koszt wywołań. Dla par podaje zgodność z referencją i zmiany po zamianie A/B. Gdy dostępne są adnotacje dwóch osób, podaje zgodność procentową i Cohen's kappa wraz z liczebnością próby.

Brakujące oceny, odmowy, błędy formatu i nieznane dane kosztowe są jawnie oznaczone. Koszt uwzględnia także ponowione i nieudane próby. Kwota pieniężna wymaga danych o cenach lub rozliczeniu dostawcy. Sukces projektu nie wymaga wykazania przewagi jednej metody.

Warianty jednego scenariusza nie są traktowane jako niezależne zadania. Kontrolowany zbiór nie określa częstości błędów agentów w rzeczywistym użyciu.

### K6. Odtwarzalny demonstrator i odporność na przerwanie

Interfejs pozwala filtrować i przeglądać trajektorie, oceny, uzasadnienia, decyzje oraz powiązane dowody. Prezentuje również porównania parami. Dostępne są eksporty CSV i JSON, wykresy oraz raport HTML.

Na zapisanych wynikach raport odtwarza się bez połączenia z API. Przerwaną partię ocen można wznowić bez utraty ukończonych wyników i bez ich duplikowania. Wznowienie zachowuje niezależność powtórzeń. Ponowienie wywołania dotyczy wyłącznie błędów technicznych i pozostaje widoczne w rejestrze prób.

Demonstracja obejmuje poprawny przebieg, błąd procesu, błąd odpowiedzi końcowej oraz naruszenie krytyczne mimo osiągnięcia celu. Pokazuje decyzje `ACCEPT`, `BLOCK` i `REVIEW`, a także powiązanie wyniku z dowodami.

### K7. Kompletność przekazania projektu

Repozytorium zawiera kod aplikacji, testy, dane demonstracyjne, rubryki, konfiguracje, surowe wyniki, raport i instrukcję. Zapis eksperymentu obejmuje wersje danych i kodu, prompt, model, parametry, czas, tokeny, wyniki i ograniczenia.

Aplikacja z bazą uruchamia się lokalnie poleceniem `docker compose up --build`. Część offline działa przez CLI bez uruchamiania serwera ani bazy. Klucze API są przekazywane przez zmienne środowiskowe i nie trafiają do danych, logów ani repozytorium.

Model i dostawca są wybierani do pilotażu, a ostateczny model, parametry i budżet są zamrażane po pilotażu. Przed testem końcowym zamrożone zostają także kod, manifest, rubryka, próg i lista par. Zmiana po obejrzeniu wyników wymaga nowego zbioru testowego albo oznaczenia analizy jako eksploracyjnej. Projekt nie wymaga lokalnego GPU ani treningu własnego modelu.
