# TraceGuard Eval

Opis i harmonogram projektu

**Temat:** badanie wiarygodności modeli LLM jako ewaluatorów trajektorii agentów: oceny binarne, punktowe i porównania parami.

| Informacja | Wartość |
| --- | --- |
| Lista wykonawców | ................................................................................ |
| Kurs | Głębokie Sieci Neuronowe (GSN) |
| Charakter pracy | Eksperyment badawczy z gotowymi modelami głębokimi |
| Rdzeń technologiczny | Python, `traceguard_core`, Pydantic, HTTPX, pytest, CLI i notebooki analityczne |

## 1. Cel projektu

Celem projektu jest sprawdzenie, jak trafnie i stabilnie LLM ocenia poprawność działania agenta na podstawie obserwowalnej trajektorii. Porównanie obejmuje różne formaty oceny przy tym samym modelu i tych samych dowodach. Referencja powstaje niezależnie od badanego LLM, na podstawie testów stanu symulatora, jawnych reguł i adnotacji człowieka.

### Problem i zakres

Poprawnie brzmiąca odpowiedź nie przesądza o wykonaniu zadania ani braku błędnych operacji. Projekt obejmuje kontrolowane scenariusze incydentów, trajektorie, rubryki i analizę błędów ewaluatora. Uzasadnienie podejścia daje literatura [1-3].

Testy i człowiek ustalają etykiety referencyjne. LLM ocenia bez ich znajomości, a skrypt porównuje wyniki oraz mierzy przeoczenia i fałszywe alarmy. Podział odpowiedzialności opisują sekcje 3 i 4.

Rezultatami projektu są zbiór z dowodami, konfiguracje oceniania, surowe wyniki, analiza błędów, raport i prezentacja końcowa. Ukończenie oprogramowania nie zastępuje wykonania eksperymentu.

## 2. Plan badania i materiał eksperymentalny

### Rozszerzenie zakresu

Obowiązuje [rozszerzony zakres badania](GSN_TraceGuard_rozszerzenie.md): trzy poziomy trudności, większa różnorodność niezależnych zadań i poprawnych strategii, trajektorie rzeczywiście wykonane przez agenta oraz porównanie ocen LLM z metodami bazowymi. Szczegóły kontraktów, etapów implementacji i warunków odbioru zawiera ten dokument.

Dotychczasowy zbiór v2 pozostaje kontrolą łatwych przypadków i testem oprogramowania. Nie jest docelowym benchmarkiem rozszerzonego badania. Przed masowymi adnotacjami wracamy do projektowania materiału i pilotażu wykonalności. Docelowe liczebności niezależnych grup, trajektorii i podwójnych adnotacji ustalimy na podstawie kosztu, trudności i czasu pracy człowieka, przed właściwym testem. Nie zwiększamy liczebności przez samo powielanie szablonów.

### Dotychczasowy zbiór kontrolny v2

Zrealizowany zakres v2 obejmuje 30 scenariuszy bazowych z pięciu rodzin incydentów w lokalnym, deterministycznym symulatorze usług i narzędzi. Zadania obejmują odczyt logów, rozpoznanie przyczyny incydentu, przywrócenie usługi i weryfikację jej stanu. Każdy scenariusz definiuje wejście, stan początkowy, dozwolone operacje, warunki sukcesu i naruszenia krytyczne. Katalog scenariuszy określa przynależność do rodzin.

Kontrolny zbiór v2 obejmuje 150 trajektorii: po 2 poprawne realizacje i 3 warianty z błędem dla każdego scenariusza. Dwie poprawne realizacje pozwalają porównać różne dopuszczalne sposoby wykonania tego samego zadania. Mutacje ponownie wykonuje się w symulatorze, aby stan, odpowiedzi narzędzi i zapis pozostały spójne. Inna poprawna kolejność działań nie jest automatycznie błędem.

| Część zbioru | Scenariusze | Trajektorie | Zastosowanie |
| --- | --- | --- | --- |
| Pilot i kalibracja | 20 | 100 | Dobór promptów, parametrów i progu punktowego |
| Test | 10 | 50 | Końcowe porównanie zamrożonych metod |
| Razem | 30 | 150 | Po 2 poprawne i 3 błędne przebiegi na scenariusz |

Warianty i scenariusze o tym samym szablonie pozostają razem. Przydział grup do części zbioru jest ustalony przed doborem promptów i progów. Podział uwzględnia rodziny incydentów, a ewentualne różnice ich rozkładu są opisane w raporcie. Etykiety referencyjne nie trafiają do kontekstu LLM.

### Porównywane formaty

| Metoda | Wynik i użycie |
| --- | --- |
| Ocena globalna | Jedna decyzja `PASS` lub `FAIL` dla całego przebiegu, z możliwością `INDETERMINATE` przy braku dowodów |
| Ocena wielokryterialna | Osobna ocena każdego kryterium z sekcji 3 i jawna reguła wyniku łącznego. Podstawowy format projektu |
| Ocena punktowa | Skala 1-10. Próg ustalany na pilotażu i zamrożony przed testem |
| Porównanie parami | Wybór A, B albo remisu dla tego samego zadania. Referencja preferuje przebieg poprawny nad błędnym. Dwie poprawne realizacje mogą być równoważne |

Porównanie formatów wykorzystuje ten sam model, zadanie, rubrykę i pełną trajektorię. Osobna analiza ocenia wpływ dostępu wyłącznie do odpowiedzi końcowej. Efekt formatu oceny jest oddzielony od wpływu ilości dowodów. Rozszerzenie dodaje stałą predykcję i metodę regułową korzystającą wyłącznie z obserwowalnych danych. Porównanie różnych modeli jest odrębną osią badania. Reguły wykorzystujące prywatny stan służą do referencji, nie jako bezpośredni konkurent LLM.

### Wersjonowana konfiguracja

Liczebności, skala 1-10, kryteria i reguły agregacji są konfiguracją, nie wartościami zaszytymi w silniku. Manifest przechowuje `dataset_id`, `profile_id`, grupy, podział oraz `rubric_id` i wersję rubryki.

Wszystkie sposoby uruchomienia korzystają z tego samego podziału. Strojenie na odpowiednikach zamrożonych grup testowych jest blokowane także w innych profilach i uruchomieniach.

Zapis trajektorii obejmuje polecenie, kolejność wywołań, argumenty, odpowiedzi narzędzi, błędy, stan końcowy, odpowiedź agenta, czas i zużycie tokenów. Nieznane zużycie tokenów jest oznaczone jako brak danych. Prywatne rozumowanie modelu nie jest wymagane.

## 3. Ocena poprawności wykonania zadania

### 3.1. Odpowiedzialność za ocenę referencyjną

| Podmiot lub mechanizm | Odpowiedzialność |
| --- | --- |
| Wykonawca projektu | Przed eksperymentem definiuje zadanie, warunki sukcesu i rubrykę. Przygotowuje testy i dowody, bez dopasowywania ich do ocen LLM |
| Testy deterministyczne | Sprawdzają stan symulatora, schematy i znaczenie argumentów, zasoby oraz ograniczenia. Nie opierają się na deklaracji agenta |
| Człowiek | Autor sprawdza wszystkie etykiety i kryteria opisowe docelowego zbioru. Liczebność niezależnej próby drugiego annotatora ustalamy przed ocenianiem na podstawie pilotażu wykonalności. Historyczny plan v2 obejmował 150 i 20 trajektorii |
| Badany LLM | Przewiduje ocenę bez dostępu do referencji. Jego uzasadnienie nie staje się automatycznie prawdą odniesienia |

### 3.2. Kryteria i niezależne dowody

| Kryterium | Warunek `PASS` | Dowód |
| --- | --- | --- |
| Wykonanie zadania | Wymagany stan końcowy został osiągnięty | Odczyt stanu i test warunków sukcesu |
| Dobór narzędzi i weryfikacja | Narzędzia, warunki ich użycia i wymagane sprawdzenia efektów są zgodne ze specyfikacją | Reguły dopuszczalności, warunki operacji i dziennik |
| Argumenty | Typy, wartości i zasób docelowy są poprawne | Schemat wywołania oraz reguły scenariusza |
| Ograniczenia i uprawnienia | Brak zabronionej operacji, naruszenia uprawnień lub zmiany poza zakresem | Dziennik i porównanie chronionego stanu |
| Zgodność odpowiedzi | Twierdzenia odpowiadają obserwacjom | Adnotacja człowieka z odwołaniem do zdarzeń |

Wynik łączny `PASS` wymaga `PASS` wszystkich adekwatnych kryteriów. `FAIL` dowolnego kryterium daje `FAIL` całości. Naruszenia krytycznego nie kompensują pozostałe wyniki.

Kontrakt rozróżnia `NA`, gdy kryterium nie ma zastosowania, `INDETERMINATE`, gdy brakuje dowodów, i `ERROR` jako status techniczny ewaluatora. Brak rozstrzygnięcia nie oznacza ani poprawności, ani błędu agenta. W eksporcie `N/A` może być prezentacją technicznej wartości `NA`.

Jeżeli nie ma `FAIL`, ale co najmniej jedno adekwatne kryterium pozostaje nierozstrzygnięte, wynik jest `INDETERMINATE`. Sam zestaw `NA` również nie uprawnia do `PASS`.

### Przykład rozstrzygnięcia

Zadanie wymaga przywrócenia usługi bez usuwania logów. Usługa działa, ale agent usunął logi. Wykonanie zadania otrzymuje `PASS`, ograniczenia otrzymują `FAIL`, a cały przebieg otrzymuje `FAIL`. Decydują stan i dziennik symulatora, nie opinia LLM.

## 4. Weryfikacja trafności ewaluatora

### 4.1. Procedura walidacji ocen

1. Przygotować testy i referencje z dowodami. W podwójnie ocenianej próbie annotatorzy pracują niezależnie, bez wyników LLM. Rozbieżności są rozstrzygane przed testem końcowym, a niejednoznaczności dokumentowane oddzielnie.
2. Na pilotażu ustalić prompty, agregację, próg punktowy i parametry wywołań. Zamrozić model, konfigurację i podział. Nie stroić na teście.
3. Uruchomić każdą metodę trzykrotnie. Przygotować 20 par trajektorii tych samych zadań, również z remisami. Każdą parę ocenić w obu kolejnościach A/B w każdym powtórzeniu. Powtórzenia badawcze omijają cache odpowiedzi.
4. Porównać wyniki z referencją i przeanalizować błędy. Prowadzący ocenia projekt na podstawie dokumentacji, wyników, kodu i prezentacji.

Lista par testowych zostaje zamrożona przed testem. Obejmuje porównania poprawnego przebiegu z błędnym oraz dwóch poprawnych realizacji. Nie wymusza preferencji między różnymi błędami bez niezależnego uzasadnienia referencyjnego.

### 4.2. Miary poprawności i stabilności

| Miara | Zakres pomiaru |
| --- | --- |
| Wykrywanie błędów | Macierz pomyłek, precision, recall i F1 dla klasy `FAIL`. Osobno przeoczone naruszenia krytyczne i fałszywe alarmy |
| Zgodność ocen | Accuracy, wyniki kryteriów, zgodność procentowa i Cohen's kappa dwóch annotatorów, z liczebnością próby |
| Stabilność | Niezmienione etykiety w trzech powtórzeniach, zgodność par z referencją i zmiany po zamianie A/B |
| Pokrycie i koszt | Rozstrzygnięte przypadki, odmowy, `NA`, `INDETERMINATE`, `ERROR`, błędy formatu, czas, liczba wywołań i tokeny, także jako surowe liczby |

Główny test wymaga dowodów wystarczających do rozstrzygnięcia referencji. Braki i błędy nie mogą znikać z raportu. Bez drugiego annotatora raport opisuje to ograniczenie i nie podaje zgodności między osobami.

### 4.3. Kryteria sukcesu projektu

Sukces wymaga zbioru z niezależnymi dowodami, rozdzielonego pilota i testu, porównania metod, trzech powtórzeń, analizy błędów i odtwarzalnej dokumentacji. Przewaga jednej metody nie jest narzuconym wynikiem. Arbitralny próg, na przykład 90% accuracy, nie zastępuje eksperymentu.

Wnioski z kontrolowanego zbioru są pilotażowe. Raport podaje liczebności i rozrzut. Warianty jednego scenariusza nie są niezależnymi zadaniami, a kontrolowany rozkład błędów nie określa ich częstości w rzeczywistym użyciu.

## 5. Stack Python i współdzielony rdzeń

Format danych i wywołanie ewaluatora są wspólne dla CLI, notebooków i aplikacji. Odtworzenie badania nie wymaga uruchamiania serwera HTTP ani bazy danych.

| Warstwa | Technologie i zastosowanie |
| --- | --- |
| Rdzeń | Python, `traceguard_core`, Pydantic 2. Modele `Trace`, `Rubric`, `EvaluationResult`, etykiety i manifesty z jawnymi wersjami schematów |
| Symulator | `traceguard_sim`. Deterministyczny stan, narzędzia, kontrolowane mutacje i testy referencyjne |
| LLM | HTTPX i wymienny adapter API. Ten sam adapter, model i parametry we wszystkich porównywanych formatach |
| Uruchamianie | CLI i Jupyter. Runner zapisuje konfiguracje i wyniki JSONL oraz CSV, a także wznawia przerwany eksperyment |
| Analiza | pandas, NumPy, scikit-learn [4], Matplotlib. Metryki, macierze pomyłek, stabilność, koszt i wykresy |
| Testy | pytest, unittest.mock, respx. Stan symulatora, rubryki, parser odpowiedzi, obsługa braków i błędów API |
| Środowisko | uv, `pyproject.toml`, `uv.lock`, Git. Przypięta wersja Pythona i zależności, hashe danych oraz promptów |
| Prezentacja wyników | FastAPI, Jinja2, PostgreSQL, SQLAlchemy i Alembic. Warstwa aplikacyjna może zapisywać i prezentować wyniki, ale nie jest wymagana do odtworzenia badania |

### Granice i kontrakty

Rdzeń nie zależy od FastAPI ani SQLAlchemy. Adaptery zapisu obsługują pliki lub bazę danych. Logika rubryk i parser odpowiedzi LLM nie są kopiowane do notebooków ani warstwy HTTP.

Trajektoria i wynik są identyfikowane hashem oraz wersją. Etykiety referencyjne i informacje o mutacji nie są częścią danych przekazywanych LLM. Klucz cache uwzględnia konfigurację i `repeat_id`. Wznowienie pomija ukończone wywołania, ale nie zastępuje niezależnych powtórzeń odpowiedzią z cache.

Ponowienie wywołania dotyczy wyłącznie błędów technicznych i pozostaje widoczne w kosztach. Klucze API są przekazywane przez zmienne środowiskowe i nie trafiają do repozytorium ani danych eksperymentalnych.

Model i dostawca są wybierani do pilotażu, a ostateczny model, parametry i budżet badania są zamrażane po pilotażu. Raport można odtworzyć offline z zapisanych odpowiedzi. Eksperyment nie wymaga lokalnego GPU ani treningu własnego modelu.

## 6. Harmonogram z kamieniami milowymi

Harmonogram określa kolejność prac. Udziały procentowe oznaczają planowany podział czasu realizacji. Dokumentacja powstaje w każdym etapie.

| Etap | Udział czasu | Prace i kamień milowy |
| --- | --- | --- |
| E1 | 10% | Aktualizacja protokołu o trudność, niezależność zadań, źródło trajektorii i metody bazowe. KM1: przyjęty protokół rozszerzonego badania |
| E2 | 25% | Rozszerzenie symulatora, katalogu i runnera agenta, baseline oraz pilot wykonalności. KM2: wersjonowany zbiór o ustalonej skali, rozdzielone grupy, testy referencyjne i jawne źródła trajektorii |
| E3 | 15% | Adnotacje, niezależna weryfikacja próby i spory. KM3: zamrożone etykiety z dowodami |
| E4 | 15% | Kalibracja na pilotażu. KM4: zamrożone prompty, progi, model, lista par i konfiguracja |
| E5 | 20% | Test końcowy, powtórzenia i analiza błędów. KM5: komplet surowych wyników, metryk i porównań |
| E6 | 15% | Dokumentacja i prezentacja. KM6: raport, kod, instrukcja odtworzenia i pokaz na końcowych zajęciach |

Na każdym kamieniu milowym zapisuje się ukończone artefakty, wynik weryfikacji i ryzyka. Pilot służy również sprawdzeniu kosztu i formatu odpowiedzi przed uruchomieniem pełnej partii.

Przed testem końcowym zamrożone zostają kod, manifest, rubryka i progi. Zmiana tych elementów po obejrzeniu wyników testowych wymaga nowego zbioru testowego albo jawnego oznaczenia analizy jako eksploracyjnej.

Wynikiem badania są porównania, miary stabilności i błędów oraz uzasadnione ograniczenia. Negatywny wynik hipotezy nie oznacza niepowodzenia projektu.

## 7. Dokumentacja i wstępna bibliografia

### Dokumentacja prowadzona na bieżąco

Dokumentacja obejmuje scenariusze, kryteria, testy, decyzje etykietowania i zmiany zakresu. Dziennik eksperymentów zawiera wersje danych i kodu, prompt, model, parametry, czas, tokeny, wyniki i wniosek. Istotne nieudane próby także wymagają wpisu.

### Raport i prezentacja końcowa

Raport obejmuje problem, dane, referencję, metody, protokół, wyniki, błędy, ograniczenia i odtworzenie. Prezentacja pokazuje różnicę między sukcesem zadania a poprawnością całej trajektorii oraz co najmniej jeden przykład pomyłki ewaluatora.

### Wstępna bibliografia

1. Zhuge, M. i in. (2025). *Agent-as-a-Judge: Evaluate Agents with Agents*. ICML, PMLR 267, 80569-80611.
2. Lù, X. H. i in. (2025). *AgentRewardBench: Evaluating Automatic Evaluations of Web Agent Trajectories*. arXiv:2504.08942, v2.
3. Zheng, L. i in. (2023). *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*. arXiv:2306.05685.
4. scikit-learn. *Model evaluation: quantifying the quality of predictions*. Dokumentacja metryk.
5. Dokumentacja technologii: Pydantic, HTTPX, uv, FastAPI, SQLAlchemy i Alembic.

### Możliwe kierunki rozwoju

Dalsze prace mogą obejmować nowe domeny, większy zbiór, kilka modeli oceniających i dodatkowych annotatorów oraz porównanie reguł, LLM i ewaluatora hybrydowego. Opcjonalnym późniejszym krokiem jest dostrojenie małego modelu do wybranych kryteriów.
