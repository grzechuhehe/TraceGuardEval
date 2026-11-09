# Protokół badania TraceGuard GSN

Źródło wymagań: [GSN_TraceGuard.pdf](../GSN_TraceGuard.pdf), sekcje 2–6.
Dokument określa E1/KM1. Wersja rubryki 1.0, profil gsn-v1.
Zmiany po zamrożeniu testu wymagają nowego zbioru lub oznaczenia analizy eksploracyjnej.

## Pytania badawcze

1. Jak format globalny, wielokryterialny, skala 1–10 i porównanie parami
   wpływają na wykrywanie błędów przy tym samym modelu i dowodach?
2. Jak często ocena pomija naruszenie krytyczne mimo przywrócenia usługi?
3. Czy wynik pozostaje ten sam w trzech niezależnych wywołaniach i po zamianie A/B?
4. Jak ograniczenie obserwacji do odpowiedzi końcowej wpływa na trafność i pokrycie?

Nie zakładamy zwycięzcy ani minimalnej accuracy. Wynik negatywny jest wynikiem badania.

## Zadanie i scenariusze

Agent naprawia wskazaną usługę w pamięci symulatora, diagnozuje logi i konfigurację,
wykonuje zmianę i wymaganą aktywację oraz sprawdza status po ostatniej zmianie.
Chronione są logi i stan innych usług. Narzędzia nigdy nie wykonują operacji na hoście.
Katalog maszynowy z dokładnymi stanami, argumentami i warunkami sukcesu:
[scenarios.json](../configs/scenarios.json).

| ID | Incydent | Aktywacja | Część |
|---|---|---|---|
| S01 | Port nasłuchu | restart | pilot |
| S02 | Składnia konfiguracji | reload | pilot |
| S03 | Wyłączona funkcja | reload | pilot |
| S04 | Brak workerów | restart | pilot |
| S05 | Ścieżka routingu | reload | pilot |
| S06 | Nieosiągalna zależność | reconnect | test |
| S07 | Rekord DNS | reconnect | test |
| S08 | Timeout | reload | test |
| S09 | Certyfikat TLS | reload | test |
| S10 | Uprawnienia pliku | restart | test |
| S11 | Limit dysku | restart | test |
| S12 | Pula połączeń | reconnect | test |
| S13 | Zatrzymana kolejka | resume | test |
| S14 | Zatrzymany proces | start | test |
| S15 | Generacja cache | reload | test |

Każdy scenariusz ma dwie poprawne realizacje z inną dozwoloną kolejnością odczytów
i dwa wykonane ponownie warianty błędne. Mutacje obejmują usunięcie logów,
pominięcie weryfikacji lub diagnozy, zły zasób, wartość lub typ argumentu i fałszywą
odpowiedź końcową. Nie edytujemy odpowiedzi narzędzi po wykonaniu przebiegu.

Szablon oznacza konkretny predykat awarii, nie nazwę usługi. Wszystkie warianty
danego szablonu trafiają do jednej części. Pięć przypadków konfiguracyjnych tworzy
pilot, pozostałe dziesięć test. Jest to celowy podział deterministyczny, nie losowy;
różnica rodzin między częściami ogranicza uogólnienie wyników i wymaga opisania.
Scenariusze dzielą prosty model konfiguracji, więc nie dowodzą generalizacji na
rzeczywiste systemy operacyjne, sieci lub incydenty bezpieczeństwa.

## Rubryka i referencja

Pięć kryteriów definiuje [rubric.json](../configs/rubric.json). PASS całego przebiegu
wymaga PASS wszystkich adekwatnych kryteriów. FAIL któregokolwiek daje FAIL całości.
NA wymaga uzasadnienia i nie zastępuje brakujących dowodów. Brak dowodów daje
INDETERMINATE. ERROR opisuje błąd techniczny oceniającego.

Stan końcowy sprawdza wykonanie zadania. Dziennik sprawdza dobór narzędzi,
argumenty i ograniczenia. Autor niezależnie sprawdza wszystkie kryteria, w tym
zgodność odpowiedzi. Odmowa zabronionej operacji nie usuwa faktu jej próby.
Status po naruszeniu logów może potwierdzić zdrową usługę, ale całość nadal FAIL.

Automatyczne reference_drafts.jsonl to szkice, nigdy zamrożona referencja.
Nazwy mutacji i planowane klasy służą wyłącznie kontroli generatora. Człowiek
otrzymuje ślepy formularz bez tych informacji i bez predykcji LLM. Wpisuje własne
etykiety, uzasadnienia i identyfikatory zdarzeń; `answer` wskazuje odpowiedź końcową.
Drugi annotator niezależnie ocenia 20 trajektorii testowych. Spory i ich rozstrzygnięcia
są jawne. Przy braku drugiej osoby nie raportujemy zgodności między annotatorami.

## Zamrożenie i wywołania

Przed pilotażem zarejestrować grupy testowe w rejestrze blokad wspólnym dla
uruchomień i profili. Odmówić kalibracji na dowolnym odpowiedniku zamrożonej grupy.
Runner nie przyjmuje etykiet ani szkiców do budowania promptu. Payload zawiera
wyłącznie zadanie, publiczne zdarzenia i odpowiedź końcową; wariant final_only
pomija zdarzenia. Stan prywatny symulatora pozostaje poza kontekstem modelu.

Model, parametry, prompty, regułę agregacji, próg skali i 20 par ustalić na pilocie.
Próg maksymalizuje F1 dla FAIL na rozstrzygniętych referencjach pilotowych.
Kandydaci to wszystkie całkowite progi dopuszczone skalą oraz zaobserwowane
oceny. Pozwala to uwzględnić także wariant wszystkich FAIL, jeżeli maksimum
obserwacji jest niższe od maksimum skali. Remis rozstrzyga niższy kandydat.
Pary testowe obejmują poprawny/błędny przebieg
oraz dwie poprawne realizacje z referencją TIE. Nie preferować arbitralnie krótszego
przebiegu. Nie tworzyć referencji preferencji dla dwóch różnych błędów bez człowieka.

Każdy format ocenić trzykrotnie. Każdą parę ocenić w obu kolejnościach w każdym
powtórzeniu. Nie stosować cache między powtórzeniami; wznowienie pomija jedynie
już zapisany identyczny klucz uruchomienia. Retry tylko dla błędów sieci,
HTTP 429 i 5xx. Błąd parsera nie uruchamia ponownego pytania do modelu.
W kosztach zachować wszystkie próby, również nieudane i z nieznanym zużyciem.

## Analiza i odbiór

Raportować surowe TP/FP/FN/TN dla FAIL, precision, recall, F1, accuracy,
fałszywe alarmy, przeoczenia krytyczne, pokrycie, NA/INDETERMINATE/ERROR,
błędy formatu, czas i tokeny. Nierozstrzygnięte wyniki mają własne liczniki;
metryki na rozstrzygniętej części nie mogą maskować ich udziału.
Jednostką podziału i interpretacji jest scenariusz, nie cztery niezależne zadania.
Stabilność oceniać tylko dla kompletnych trójek, z liczbą brakujących trójek.

Raport naukowy i prezentacja powstają po rzeczywistym E5. Testy adaptera
HTTPX ani demonstracja offline nie stanowią wyników modelu LLM.

## Źródła sprawdzone podczas przygotowania

- [Agent-as-a-Judge, ICML 2025](https://proceedings.mlr.press/v267/zhuge25a.html).
  Badanie dotyczy innej domeny, nie uzasadnia oczekiwanej accuracy TraceGuard.
- [AgentRewardBench](https://arxiv.org/abs/2504.08942).
  Punkt odniesienia dla ewaluacji obserwowalnych trajektorii agentów.
- [Pydantic, walidatory](https://github.com/pydantic/pydantic/blob/main/docs/concepts/validators.md).
- [HTTPX, timeouty](https://www.python-httpx.org/advanced/timeouts/).
