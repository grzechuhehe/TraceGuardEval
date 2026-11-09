# Dziennik realizacji GSN

## 27.10.2026

Źródła: GSN_TraceGuard.pdf, PP_TraceGuard.pdf, handoff_TraceGuard.md.
Brak wcześniejszego kodu w katalogu. Zainicjowano Git na gałęzi
`work/gsn-implementation`. Nie zmieniano dokumentów PDF.

| Etap | Stan | Artefakty i ograniczenia |
|---|---|---|
| E1 / KM1 | Zrealizowany | docs/protocol.md, configs/scenarios.json, rubric.json, profile GSN/PP |
| E2 / KM2 | Zrealizowany | 15 scenariuszy, 60 trajektorii, manifest 20/40, replay i testy reguł |
| E3 / KM3 | Narzędzia gotowe, adnotacje oczekują | Ślepe formularze, kontrola dowodów i sporów, zamrożenie; brak ręcznych etykiet |
| E4 / KM4 | Narzędzia gotowe, pilot oczekuje | Adapter, parsery, rejestr grup, kalibracja skali, konfiguracja i pary; model i budżet do wyboru |
| E5 / KM5 | Narzędzia gotowe, badanie oczekuje | Runner z powtórzeniami/wznowieniem, metryki i eksport offline; brak wyników LLM |
| E6 / KM6 | Instrukcja bieżąca | README i notebook; raport naukowy oraz prezentacja wymagają E5 |

## Decyzje

- Wymagania PDF i polecenie rozpoczęcia implementacji stanowią zgodę na opisany
  stack. Nie dodano FastAPI, bazy ani nieokreślonego dostawcy modelu.
- Lokalny symulator nie wykonuje poleceń systemowych. Czasy operacji są
  deterministycznymi jednostkami symulacji, nie benchmarkiem rzeczywistego systemu.
- Szkice referencyjne zachowują INDETERMINATE dla zgodności odpowiedzi.
  Planowanych klas generatora nie wolno traktować jako ludzkiej referencji.
- Pilot obejmuje pięć przypadków konfiguracji; test inne rodziny incydentów.
  Nie losowano przypadków. Tę różnicę rozkładu trzeba zachować w ograniczeniach raportu.
- PP pozostaje osobnym profilem; generator 120 przypadków i aplikacja PP nie są
  częścią zleconej realizacji GSN.
- Nie było narzędzia update_plan; stan utrzymywany jest w tym dzienniku i planie.

## Walidacja i obserwacje

- Testy kontraktów, danych, adnotacji, adaptera, runnera, metryk i workflow
  napisano przed implementacją odpowiednich modułów; potwierdzono ich początkowe błędy.
- Pierwszy build edytowalny powstał przed utworzeniem pakietów; ponowna instalacja
  pakietu po dodaniu źródeł rozwiązała brak ścieżki importu.
- Test braku etykiety w identyfikatorze poprawiono na sprawdzanie SHA-256 treści.
  Podciąg `bad` może legalnie wystąpić w losowym zapisie szesnastkowym hasha.
  Kontrola braku prywatnych pól w payloadzie pozostaje osobnym testem.
- Pierwszy pełny przebieg: 39 testów zaliczonych. Końcowy wynik i review są
  zapisywane poniżej po weryfikacji bieżącego kodu.

## Końcowa kontrola implementacji

- `bash scripts/verify.sh`: 48 testów zaliczonych, walidacja 60 trajektorii,
  kompilacja źródeł oraz build wheel i sdist zakończone powodzeniem.
- Wheel uruchomiono poza repozytorium w odrębnym środowisku Python 3.12.
  Wygenerował ten sam dataset_id i zwalidował cały zbiór.
- Wszystkie komórki kodu notebooka wykonano offline. Brak danych z badania
  został jawnie zakomunikowany; nie wygenerowano zastępczych wyników.
- Niezależny przegląd przez subagenta w ramach superpowers:requesting-code-review
  wykrył sześć problemów. Wszystkie poprawiono z regresjami w
  tests/test_review_regressions.py oraz z poprawionym testem workflow:
  przestrzeń progów; wersje kodu/promptu kalibracji; trwałość kosztów retry;
  całkiem brakujące trójki; niepełny zestaw kryteriów; nieprawidłowe usage API.
- Dodatkowo walidowane są schemat rubryki i hashe treści wyników/prób.
  Zmienione oczekiwanie progu 1 zastąpiono optimum 8, którego F1 dla testowego
  przykładu wynosi 2/3. Nie osłabiono testów.
- E3 przygotowano w data/annotation_tasks: 60 pustych formularzy autora
  oraz 20 drugiego annotatora. Próbę ustalono przed ocenianiem jako dwa
  leksykograficznie najmniejsze identyfikatory na scenariusz testowy.
  Żaden formularz nie został oznaczony jako sprawdzony.

## Najbliższe działania badawcze

1. Autor ocenia 60 trajektorii; drugi annotator niezależnie 20 testowych.
2. Rozstrzygnąć rozbieżności i zamrozić referencje z dowodami.
3. Wybrać model, dostawcę i budżet po oszacowaniu kosztu małej partii pilotowej.
4. Przeprowadzić pilot wszystkich formatów i warunków dowodów, zamrozić E4.
5. Wykonać E5 bez zmiany konfiguracji po obejrzeniu testu.
6. Przygotować raport i prezentację na podstawie rzeczywistych rezultatów.
