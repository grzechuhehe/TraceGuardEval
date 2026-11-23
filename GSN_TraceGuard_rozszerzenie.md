# Rozszerzony zakres badania TraceGuard

## Decyzja i stan wykonania

Użytkownik zatwierdził cztery zmiany: zróżnicowanie trudności, większą liczbę niezależnych zadań i strategii, trajektorie rzeczywistego agenta oraz porównanie z metodami bazowymi.

Dokument określa nowy zakres i kolejność implementacji. Nie potwierdza istnienia nowego zbioru ani wykonania eksperymentów. Obecne v1 i v2 pozostają bez zmian. V2 służy jako kontrola łatwych przypadków i regresja warsztatu; nie jest docelowym benchmarkiem rozszerzonego badania. Wstrzymujemy masowe adnotowanie v2.

## 1. Trudność oceniania

Trudność określamy przed wywołaniami ewaluatora na podstawie własności zadania i dowodów, nie odsetka błędów wybranego LLM.

- Łatwy: pojedyncza usterka, krótkie wykonanie, jawne naruszenie lub jednoznaczny sukces. V2 pozostaje kontrolą tego poziomu.
- Średni: kilka ustawień lub usług, warunki wstępne operacji, diagnoza wymagająca kilku obserwacji, więcej niż jedna poprawna strategia.
- Trudny: zależności między usługami, interakcje napraw, skutki uboczne, cofnięte zmiany, sukces chwilowy zamiast trwałego oraz błędy wymagające połączenia odległych zdarzeń.

Nie utożsamiamy długości z trudnością. Osobno oznaczamy długość, liczbę zasobów, liczbę usterek, zależności czasowe i odległość dowodu od naruszenia. Kontrolowane pary mogą różnić się jedną istotną operacją. Jeżeli dodajemy nieistotne zdarzenia, ponownie wykonujemy całość, aby zachować spójność stanu.

Braki dowodów tworzą osobny warunek badawczy z referencją INDETERMINATE, nie niejawny sposób utrudnienia głównego testu z rozstrzygalną referencją.

## 2. Niezależność zadań i strategie

Nowy katalog ma obejmować różne mechanizmy awarii, topologie zależności, warunki operacji i ograniczenia. Zmiana nazwy usługi, parametru lub wartości nie tworzy nowego niezależnego zadania.

Wprowadzamy jawne grupowanie rodziny szablonów. Wszystkie warianty, strategie, mutacje i kontrfaktyczne pary jednej grupy pozostają w tej samej części zbioru, także między wersjami. Historyczne grupy testowe nie przechodzą do pilotażu pod nowymi identyfikatorami.

Poprawne strategie mają różnić się sposobem rozwiązania, nie tylko kolejnością dwóch odczytów. Przykłady do implementacji to naprawa konfiguracji albo przywrócenie poprawnej wersji oraz naprawa zależności przed odtworzeniem usługi. Dopuszczalność zależy od konkretnej specyfikacji zadania. Referencja sprawdza warunki i stan, nie zgodność z jedną listą operacji.

Docelową liczbę niezależnych grup i trajektorii ustalimy po pomiarze kosztu oraz czasu adnotacji w pilotażu. Nie zastępujemy projektu badania arbitralną liczbą tysięcy podobnych przebiegów.

## 3. Trajektorie wykonane przez agenta

Obok przebiegów skryptowych zbieramy sesje, w których model sam wybiera kolejne narzędzie i argumenty na podstawie zadania oraz odpowiedzi symulatora. Samo wygenerowanie tekstu przypominającego log nie jest trajektorią agenta.

Agent otrzymuje wyłącznie obserwacje i dostępne narzędzia. Nie widzi prywatnego stanu, referencji, planowanych klas ani informacji o mutacji. Po każdym wywołaniu operację wykonuje symulator. Niepoprawne wywołania pozostają w dzienniku.

Runner agenta ma limity liczby kroków, tokenów, wywołań i czasu. Zapisuje pochodzenie trajektorii, konfigurację modelu, surowe odpowiedzi, operacje, koszty i przyczynę zakończenia. Osiągnięcie limitu nie jest automatycznie technicznym ERROR ewaluatora; oceniamy dostępny przebieg według rubryki.

Wyniki agentów nie zapewniają z góry równych liczebności PASS i FAIL. Raport rozdziela naturalnie zebrane trajektorie od celowo skonstruowanych mutacji. Model generujący trajektorię i model oceniający mają osobne role i konfiguracje.

## 4. Metody bazowe i modele oceniające

Porównujemy co najmniej dwie jawne metody bazowe bez LLM:

- Stałą predykcję, której klasa jest wybrana na referencjach pilotowych, a nie testowych.
- Konserwatywną metodę regułową wykorzystującą wyłącznie te same obserwowalne dane i publiczną specyfikację co LLM. Przy braku podstaw do oceny zwraca INDETERMINATE.

Reguły referencyjne korzystające z prywatnego stanu symulatora nie są uczciwym konkurentem LLM. Pozostają źródłem referencji. Wyniki metody bazowej nie są podpowiedzią dla annotatora.

Cztery formaty ocen porównujemy wewnątrz tego samego modelu. Porównanie między modelami raportujemy osobno; wybór co najmniej dwóch ewaluatorów jest celem rozszerzonego pilotażu, zależnym od dostępnego API i budżetu. Zmiana dostawcy nie może być mylona ze zmianą formatu oceny.

## Protokół i analiza

- Podział grup jest zarejestrowany przed doborem promptów, progów i agentów zbierających materiał. Kalibracja nie wykorzystuje odpowiedników grup testowych.
- Najpierw sprawdzamy działanie nowego środowiska i koszty na grupach rozwojowych. Test końcowy pozostaje niewykorzystany do strojenia.
- Referencje nadal wynikają z testów stanu i niezależnej oceny człowieka. Zwiększenie liczby danych wymaga oszacowania pracy annotatorów, nie automatycznego podpisania etykiet jako ludzkich.
- Raport rozdziela poziomy trudności, rodziny zadań, źródło trajektorii, model i dostęp do dowodów. Podaje liczebności grup, pokrycie i brakujące wyniki.
- Główne metryki pozostają oparte na FAIL: precision, recall, F1, przeoczenia krytyczne i fałszywe alarmy. Zachowujemy analizę stabilności i kolejności A/B.
- Niepewność wyników szacujemy z uwzględnieniem grup scenariuszy, np. przez bootstrap grupowy. Warianty i powtórzenia nie są traktowane jak nowe niezależne zadania.
- Listę par, model, konfigurację, kod, dane i reguły wyboru prób zamrażamy przed końcowym testem. Zmiany po wynikach wymagają nowego testu lub oznaczenia analizy eksploracyjnej.

## Kolejność implementacji i odbioru

1. Rozszerzyć kontrakty i symulator o kilka zasobów, zależności, warunki operacji, wersje konfiguracji i kontrolę skutków ubocznych. Zachować odczyt i replay v1/v2.
2. Przygotować mały katalog rozwojowy wszystkich trzech poziomów, różne strategie i kontrolowane pary. Testy muszą rozpoznawać błędy na podstawie wykonania, bez odczytywania nazwy mutacji.
3. Dodać ograniczony budżetem runner agenta, a następnie zbierać rzeczywiste trajektorie. Najpierw testy z atrapą API, potem jawnie zatwierdzona partia zdalna.
4. Dodać stały i obserwowalny regułowy baseline. Sprawdzić brak dostępu do prywatnego stanu i referencji testowych.
5. Wykonać pilotaż wykonalności: trudność, rozkład błędów agentów, czas adnotacji i koszt. Jeżeli łatwe przypadki dają efekt sufitu, nie usuwać ich po cichu; raportować osobno.
6. Ustalić docelową liczebność grup, próbę podwójnej adnotacji i budżet porównania modeli. Utworzyć wersjonowany profil badania przed właściwą kalibracją.
7. Przeprowadzić adnotacje, kalibrację, zamrożenie i test według zaktualizowanych E3-E6.

## Nierozstrzygnięte ograniczenia zewnętrzne

Termin nie jest ograniczeniem. Dla aktywnego celu przyjmujemy konserwatywnie maksymalnie 10 USD API/model/miesiąc, a dla Anthropic dodatkowo 20 USD łącznie miesięcznie. Deklaracja o subskrypcji ChatGPT nie potwierdza kredytu API. Limity subskrypcji są oddzielne od dolarów API. Grok pozostaje niedopuszczony do płatnych wywołań bez uzgodnionej ceny i limitu.

Konkretne modele, cenniki i uprawnienia kont nadal nie zostały potwierdzone. Oficjalne dokumentacje rozróżniają API OpenRouter, natywne Messages Anthropic oraz programowe interfejsy agentów Codex i Cursor; nie są to automatycznie zamienne protokoły. Nowy pionowy wycinek działa wyłącznie z MockTransport. Płatne partie CLI są wstrzymane do czasu potwierdzenia dostępu i walidacji cennika oraz tokenizacji. Klucze pozostają poza plikami projektu.
