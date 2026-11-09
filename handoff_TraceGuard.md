# Przekazanie projektu TraceGuard

Stan na 27.10.2026. Dokument dla kolejnego agenta, nie dla prowadzącego.

## Cel kolejnej sesji

Kontynuować TraceGuard na podstawie aktualnych specyfikacji. Użytkownik wcześniej wskazał rozpoczęcie prac od początku harmonogramu GSN i wykonanie przewidzianych tam zadań. Obecne wywołanie dotyczy wyłącznie przygotowania przekazania; w tej sesji nie rozpoczęto implementacji.

TraceGuard bada wiarygodność LLM oceniających trajektorie agentów obsługi incydentów. Wspólny projekt ma część badawczą GSN oraz część aplikacyjną PP. Poniższe odnośniki prowadzą do źródeł szczegółowych wymagań. Nie odtwarzaj specyfikacji z historii rozmowy.

## Aktualne dokumenty

| Dokument | Źródło | Status |
|---|---|---|
| GSN_TraceGuard.pdf | https://chatgpt.com/library?file_id=libfile_617dac7cb9e881918b16591f4c7a0672&account_id=personal | 7 stron; aktualną treść odczytano w tej sesji; opis badania, ocena poprawności i harmonogram |
| PP_TraceGuard.pdf | https://chatgpt.com/library?file_id=libfile_1188ddd5d6248191bec443a8680c6c75&account_id=personal | 3 strony; aktualną treść odczytano w tej sesji; tabela otwierająca, definicja problemu, stack i kryteria sukcesu |
| PP_TraceGuard.pdf, wcześniejszy obszerny dokument | https://chatgpt.com/library?file_id=libfile_420ab63206408191949dfe021a74e7be&account_id=personal | 11 stron; pomocniczy materiał historyczny; nie zastępuje nowszego dokumentu 3-stronicowego |

Dokumenty zostały odczytane przez narzędzie Library. Nie pobrano ich lokalnych plików PDF. Historyczne ścieżki sandbox z poprzednich rozmów nie są gwarantowanym źródłem. Gdy potrzebne będą bajty albo edycja, pobierz właściwy dokument z powyższego źródła. Przy aktualizacji zachowaj jego tożsamość Library.

## Ustalenia obowiązujące

- Python jest wspólnym stackiem. Java/Spring były wcześniejszą propozycją i zostały zastąpione.
- GSN obejmuje eksperyment z gotowymi modelami głębokimi. Trening własnego modelu nie jest wymagany; może wystąpić wyłącznie jako dalszy kierunek rozwoju.
- PP obejmuje aplikację używającą wspólnego rdzenia. GSN musi działać przez CLI i notebooki bez uruchamiania HTTP ani bazy danych.
- Szczegóły stacku są w GSN, sekcja 5, i PP, sekcja 2. Rdzeń `traceguard_core` nie zależy od FastAPI ani SQLAlchemy. Symulator przewidziano jako `traceguard_sim`.
- Oceny referencyjne powstają niezależnie od badanego LLM. Testy sprawdzają stan symulatora i jawne reguły, człowiek sprawdza etykiety i kryteria opisowe, a skrypt porównuje predykcje z referencją. Prowadzący dokonuje odbioru projektu na podstawie jego rezultatów.
- Ocena rezultatu zadania i ocena poprawności całego przebiegu to różne rzeczy. Przywrócenie usługi z naruszeniem zakazu usuwania logów daje FAIL całego przebiegu.
- Negatywny wynik hipotezy badawczej jest dopuszczalnym rezultatem projektu.

## Różnice między profilami, których nie wolno przypadkiem usunąć

GSN i PP współdzielą oprogramowanie, ale opisują różne konfiguracje eksperymentów. GSN, sekcja 2, określa 60 trajektorii z 15 scenariuszy, podział 20/40, skalę 1–10 oraz porównania parami. Aktualny PP, sekcja 3, określa docelowo 120 trajektorii z 30 scenariuszy, podział 80/40 oraz porównanie PASS/FAIL ze skalą 1–5. Mniejszy zakres PP jest jawnie pilotem.

Liczebności, rubryki, skale i reguły agregacji mają być konfiguracją profilu. Nie ujednolicaj ich po cichu i nie wpisuj jednej wersji na stałe do silnika. Współdzielenie danych nie może doprowadzić do strojenia na odpowiednikach zamrożonych grup testowych.

Wynik kryterium odróżnia PASS, FAIL, NA i INDETERMINATE; ERROR jest statusem technicznym. PP definiuje dodatkowo decyzje ACCEPT/BLOCK/REVIEW. Reguły i pierwszeństwo decyzji sprawdź w aktualnym PP, kryterium K4. Braku dowodów nie zamieniaj na poprawność ani błąd agenta.

## Harmonogram i najbliższe działanie

Harmonogram GSN znajduje się w sekcji 6 aktualnego PDF. Pierwszy etap E1 obejmuje definicję pytań, scenariuszy i rubryki; kamień KM1 to opis zadania, kryteria i zasady referencji. To punkt startowy przy wznowieniu prac. Następne etapy obejmują symulator i zbiór, adnotacje, kalibrację, test końcowy oraz raport i prezentację.

Przed implementacją sprawdź wskazane przez użytkownika repozytorium i jego instrukcje. Jeśli repozytorium nie zostało podane, nie twierdź, że istnieje. Przy realizacji E1 przygotuj konkretne artefakty wymagań, scenariuszy i rubryki zgodne z PDF, wraz ze sposobem ich późniejszej weryfikacji. Bieżąca dokumentacja jest wymagana przez cały projekt.

Historyczny punkt kontrolny PP to 25.11 / 02.12.2026. Nie dopisuj go automatycznie do aktualnej 3-stronicowej specyfikacji, którą użytkownik celowo ograniczył do trzech sekcji i tabeli otwierającej. Dokładnych dat etapów GSN nie ustalono; PDF używa kolejności i udziałów czasu.

## Stan wykonania i granice wiedzy

- W tym przekazaniu zweryfikowano dokumenty. Nie potwierdzono istnienia implementacji, danych, działającego symulatora ani wyników eksperymentów.
- Bieżący katalog roboczy `/workspace/scratch/72eb01b31876` nie zawiera widocznych plików projektu. Nie jest to dowód braku kodu w innych miejscach.
- W tej sesji nie uruchamiano testów aplikacji, nie wywoływano modeli i nie modyfikowano PDF-ów.
- Model judge’a, dostawca i budżet API pozostają do wyboru po pilotażu. Nie zakładaj dostępności kluczy ani GPU.
- GSN planuje drugiego niezależnego annotatora dla części próby. Specyfikacja opisuje plan; dostępność tej osoby nie została potwierdzona.
- Bibliografii nie weryfikowano ponownie w internecie podczas przygotowywania przekazania. Przed badaniami lub twierdzeniami o nowości sprawdź źródła pierwotne.

## Preferencje użytkownika

Odpowiadaj po polsku, krótko i konkretnie. Materiały dla prowadzącego mają być gotowe do oddania: bez numerów wersji, komentarzy do użytkownika i odniesień do innych kursów lub magisterki. Dane osobowe użytkownik dodaje sam. Dokumenty GSN i PP mają mieć wspólne czcionki, rozmiary, kolorystykę, tabele i stopki.

W historii pojawił się też osobny pomysł GSN dotyczący rekomendacji manewrów NFL Big Data Bowl 2027. Późniejsze wiadomości wróciły do wspólnego TraceGuard GSN+PP. Nie przenoś zakresu NFL do tego projektu bez nowej instrukcji użytkownika.

## Sugerowane umiejętności

- `openai-library:library`: aktualne dokumenty, pobranie plików i zapis rezultatów.
- `pdf`: odczyt lub modyfikacja PDF oraz sprawdzenie układu po zmianach.
- `superpowers:writing-plans`: rozpisanie realizacji zatwierdzonych wymagań przed kodowaniem.
- `mattpocock-skills:implement`: wykonanie pracy na podstawie specyfikacji, gdy użytkownik zleci implementację.
- `superpowers:verification-before-completion`: weryfikacja rzeczywistych rezultatów przed stwierdzeniem ukończenia.

Oryginalnie wywołana lokalna umiejętność `mp-handoff` pod ścieżką WSL nie była dostępna w tym środowisku. Użyto dostępnej `mattpocock-skills:handoff`. Nie zmieniano ani nie instalowano umiejętności. Nie zawarto kluczy, danych osobowych ani danych dostępowych.
