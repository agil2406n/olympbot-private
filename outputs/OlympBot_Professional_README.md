# OlympBot Demo Terminal v6.3 — 1 dəqiqə Auto Demo / Server 24/7

## İşə salmaq

1. Hazırda açıq olan köhnə bot terminalını `Ctrl+C` ilə dayandırın və onun açdığı OlympTrade pəncərəsini bağlayın.
2. `OlympBot_Professional.bat` faylını iki dəfə klikləyin.
3. Açılan terminalda dörd yoxlamanın tamamlanmasını gözləyin: Python, paketlər, Chromium və brauzerin başladılması.
4. OlympTrade və peşəkar idarəetmə paneli avtomatik açılacaq.
5. OlympTrade hesabınıza daxil olun.

Panel yalnız OlympTrade-in **Deneme/Demo hesabı** ilə işləyir. Ayrı virtual `$10.000` hesabı yaratmır və platforma qoşulmayanda əməliyyat açmır.

v6.1-dən etibarən avtomatik Demo icrası başlanğıcdan hazır vəziyyətdədir.
OlympTrade hesabı `Deneme hesabı` kimi təsdiqlənən kimi uyğun 1 dəqiqəlik
siqnal platformaya avtomatik göndərilir. Paneldə `OLYMP DEMO` görünməsi icranın
hazır olduğunu bildirir. Real hesab görünərsə klik hər əmrdən əvvəl bloklanır.

Botun bazası və jurnalları `outputs/runtime` qovluğunda saxlanılır. Əvvəlki giriş sessiyasını qorumaq üçün mövcud `Desktop\Olymptrade\olymp_user_data` brauzer profili avtomatik istifadə edilir; buna görə hesab məlumatlarını yenidən yazmaq tələb olunmur. Həmin profil mövcud deyilsə yeni profil `outputs/runtime/browser-profile` altında yaradılır.

Brauzer başlaya bilməzsə panel artıq sonsuz “Yüklənir” göstərmir; qırmızı sahədə konkret başlanğıc xətasını göstərir. Köhnə donmuş proses `5000` portunu tutarsa yeni bot avtomatik `5001`–`5009` aralığında boş porta keçir və yeni panel səhifəsini açır.

## Panel imkanları

- Canlı websocket bağlantı statusu
- Hər aktiv üçün canlı `YUXARI ↑`, `AŞAĞI ↓` və `GÖZLƏ` siqnal kartı
- 0–100 siqnal gücü, qərar səbəbləri, trend rejimi və volatilite
- Təsdiqlənmiş siqnal üçün 60 saniyəlik istiqamət kilidi və geri sayım
- `YUXARI/AŞAĞI NAMİZƏD` ilə real aktiv siqnalın aydın ayrılması
- Başlanma/bitmə saniyəsi və sessiyalararası təsdiqlənmiş siqnal tarixçəsi
- Güclü siqnal ilə avtomatik Demo icrasına hazır siqnalın ayrı göstərilməsi
- Açıq OlympTrade aktivləri arasında əməliyyatsız canlı tick rotasiyası
- `LIVE TICKS`, `RECENT TICKS`, `OHLC axını` və `axın yoxdur` mənbə statusu
- Aktivlər və son qiymətlər
- Yaşıl/qırmızı OHLC şam qrafiki
- 1, 5 və 15 dəqiqəlik timeframe seçimi
- EMA 3 və EMA 8 giriş indikator xətləri
- Ayrı RSI 9 paneli və strategiyanın 72/54/46/28 sərhədləri
- Gold olmadan 5 aktivlik skaner: BNB OTC, EUR/USD, Bitcoin, Ethereum və AUD/CAD
- OpenAI ilə ikinci mərhələ siqnal təsdiqi və Azərbaycan dilində qısa səbəb
- Siqnal və əməliyyat giriş markerləri
- Qrafik zoom-u və şam üzərində OHLC/tick məlumatı
- OlympTrade brauzerə göndərdiyi tarixi OHLC/tick paketlərinin avtomatik idxalı
- Toplanan şamların SQLite-da saxlanması və növbəti açılışda dərhal bərpası
- RSI/EMA üçün şam hazırlıq göstəricisi
- Siqnal və əməliyyat hadisələri
- Ticarət növbəsi və gözləyən platforma nəticələri
- OlympTrade Deneme hesabından oxunan faktiki balans
- Paneldən seçilən və platformanın məbləğ sahəsinə yazılan əməliyyat məbləği
- Platforma balans dəyişməsindən hesablanan P&L və win-rate
- SQLite əməliyyat tarixçəsi
- Martinqeylsiz sərt risk mühərriki və avtomatik günlük dayanma
- Tamamlanmış 1 dəqiqəlik şamlarla look-ahead olmayan tarixi backtest
- Aktiv üzrə win-rate, vahid P&L, gözlənti və maksimum drawdown
- Əməliyyat tarixçəsinin paneldən UTF-8 CSV ixracı
- OlympTrade Deneme hesabını iki təhlükəsizlik işarəsi ilə təsdiqləmək
- Deneme hesabında Yukarı/Aşağı əmrləri göndərmək
- Botu təhlükəsiz dayandırma düyməsi

## OlympTrade Deneme hesabına qoşulmaq

1. OlympTrade-də sağ yuxarıdakı hesab menyusundan `Deneme hesabı` seçin.
2. Paneldə `Deneme hesabı təsdiqləndi` statusunu gözləyin.
3. Məbləğ sahəsinə istədiyiniz tam demo məbləğini (məsələn `100`) yazın və `Məbləği yaz` düyməsini basın.
4. Paneldə `Platformda görünən məbləğ` hissəsində eyni rəqəmin göründüyünü yoxlayın.
5. Paneldə rejimin avtomatik `OLYMP DEMO` vəziyyətinə keçdiyini yoxlayın.
6. Avtomatik icranı dayandırmaq istəsəniz `Platform Demo ayır` düyməsini basın.
   Sonradan yenidən qoşarkən təhlükəsizlik üçün `DEMO` təsdiqi tələb olunur.

Bot hər əmrdən əvvəl seçilmiş hesab etiketinin məhz `Deneme hesabı`, `Demo account` və ya `Practice account` olduğunu yoxlayır. Real/Live hesab etiketi görünərsə Yukarı/Aşağı klikləri bloklanır. Platformanın göstərdiyi dildən asılı olaraq əlavə təhlükəsizlik cümləsi də yoxlanılır, amma bütün dillərdə görünmədiyi üçün məcburi deyil.

Bot məbləği OlympTrade-dəki `+`/`−` idarəsi ilə qurur və klikdən əvvəl yenidən yoxlayır. Məsələn balans `₼10.000,00`, məbləğ `100` olduqda itirilən əməliyyatdan sonra platformanın öz balansı `₼9.900,00` olur; panel də məhz həmin balansı göstərir. Müddət `1 dəqiqə`dir və Martingale tətbiq edilmir.

Nəticə lokal qiymət simulyasiyasından deyil, əməliyyat bitdikdən sonra OlympTrade Deneme balansının əvvəlki balansla fərqindən götürülür. Yerli SQLite bazası yalnız jurnal və statistika üçündür.

Bot hər tamamlanmış şam üçün çoxfaktorlu bal hesablayır:

- qiymət axını qoşulmalıdır;
- ən azı 51 tamamlanmış bir dəqiqəlik şam toplanmalıdır;
- YUXARI üçün EMA 3, EMA 8-dən yuxarı, əsas EMA 15 isə EMA 50-dən
  yuxarı olmalı; RSI 9 göstəricisi `54–72` aralığında qalmalıdır;
- AŞAĞI üçün EMA 3, EMA 8-dən aşağı, əsas EMA 15 isə EMA 50-dən
  aşağı olmalı; RSI 9 göstəricisi `28–46` aralığında qalmalıdır;
- siqnal istiqamətində son bir dəqiqəlik momentum və ən azı `25%`
  şam gövdəsi təsdiqi olmalı, ümumi güc minimum `75/100` toplamalıdır;
- yüksək volatilite və yan bazar avtomatik Demo icrasını bloklayır;
- eyni aktiv üzrə siqnallar arasında ən azı səkkiz tamamlanmış şam gözlənilir;
- avtomatik Demo üçün aktivin ən azı 30 tarixi siqnalı, son 30%-də ən azı
  10 siqnalı və hər iki hissədə minimum `1.0` profit factor-u olmalıdır;
- hər aktiv ayrıca hesablanır və eyni anda yalnız bir Demo əməliyyatına icazə verilir;
- klikdən əvvəl OlympTrade-də siqnalın aid olduğu aktiv yenidən təsdiqlənir.

Server paketində əlavə nəzarətli `DEMO_LEARNING_MODE` mövcuddur. Bu rejim yalnız
OlympTrade Deneme hesabı hər klikdən əvvəl təsdiqləndikdə, strategiya siqnalı bütün
giriş filtrlərini keçdikdə və bal ən azı `DEMO_LEARNING_MIN_SCORE=90` olduqda işləyir.
Server xidməti OlympTrade Demo rejimində günlük əməliyyat, günlük zərər,
ardıcıl zərər və stake-faiz dayandırma limitlərindən istifadə etmir. Mövcud Demo
balansı və eyni anda yalnız bir açıq əməliyyat yoxlamaları qalır. Real hesab
qoruması və martinqeyl qadağası bu rejimdə də dəyişmir.

Aktiv skaneri yalnız OlympTrade-də həqiqətən açıq olan tablar arasında keçir. Paneldə
`Skan` düyməsinin üzərində açıq aktiv sayı, üzərinə toxunduqda isə mövcud və açıq
olmayan aktiv kodları görünür.

Minimum balı və bütün təhlükəsizlik filtrlərini keçməyən istiqamət yalnız
`YUXARI NAMİZƏD` və ya `AŞAĞI NAMİZƏD` kimi göstərilir; bu, əməliyyat
siqnalı deyil. Təsdiqlənmiş `YUXARI ↑` və ya `AŞAĞI ↓` siqnalı yarandıqda
istiqamət növbəti bir dəqiqəlik əməliyyat pəncərəsinin sonuna qədər kilidlənir.
Kartda qalan saniyə görünür və bu müddətdə ani qiymət dəyişməsi siqnalı
`GÖZLƏ` vəziyyətinə çevirmir.

Canlı siqnal kartlarının altında `Siqnal tarixçəsi` yerləşir. Burada hər
təsdiqlənmiş siqnalın aktiv kodu, YUXARI/AŞAĞI istiqaməti, gücü, dəqiq
başlanma vaxtı, bitmə vaxtı və `AKTİV/BİTİB` statusu görünür. Tarixçə son
30 bot sessiyasının jurnalından bərpa edilir və bot yenidən başladıqda itmir.

## Risk limitləri

Martinqeyl kod səviyyəsində söndürülüb və mühit parametri ilə aktiv edilə
bilməz. Bot hər siqnaldan əvvəl UTC günü üzrə aşağıdakı limitləri yoxlayır:

- maksimum günlük zərər: `100` balans vahidi;
- maksimum günlük əməliyyat: `20`;
- maksimum ardıcıl zərər: `3`;
- bir əməliyyatın maksimum məbləği: cari Demo balansının `1%`-i.

Limitlərdən biri dolduqda yeni əməliyyat avtomatik bloklanır və səbəb paneldə
`Risk mühərriki` sətrində görünür. Bunlar başlanğıc dəyərləridir; BAT faylını
dəyişmədən `MAX_DAILY_LOSS`, `MAX_DAILY_TRADES`,
`MAX_CONSECUTIVE_LOSSES` və `MAX_STAKE_PERCENT` mühit dəyişənləri ilə daha
sərt edilə bilər.

## Backtest və CSV

Panelin aşağısındakı backtest yalnız bazada saxlanmış tamamlanmış 1 dəqiqəlik
şamları və paneldə işləyən eyni One Minute Trend v6 qaydasını istifadə edir.
Siqnal `i` şamının bağlanışında hesablanır, nəticə isə
yalnız sonrakı `i+1` şamının bağlanışından götürülür. Son, hələ formalaşan şam
hesaba qatılmır. Son 30% ayrıca OOS sahəsində göstərilir. OpenAI filtri
backtestə daxil deyil.

`Hesabat CSV` düyməsi son 500 Demo əməliyyatını vaxt, aktiv, istiqamət,
məbləğ, giriş/çıxış, indikatorlar, nəticə və P&L sütunları ilə endirir. API
açarı və brauzer sessiyası hesabatda olmur.

Digər lokal proqramlar cari siqnal kartlarını JSON kimi
`http://127.0.0.1:5000/api/signals` ünvanından oxuya bilər. Endpoint yalnız
analiz nəticəsini verir və özü əməliyyat açmır.

Platformadan canlı axın gəlməyən aktiv `Məlumat gözlənilir` kimi göstərilir və
onun üçün əməliyyat açılmır.

## Tick və OHLC axını

OlympTrade xam tick-ləri əsasən hazırda seçilmiş aktiv üçün göndərir. Digər
aktivlər dəqiqəlik OHLC şam yenilənməsi ala bilər; bu halda əvvəlki paneldə
görünən `0 tick/şam` xəta deyil, tick sayının həmin paketdə olmaması idi.
Terminal artıq bunu `OHLC axını · tick sayılmır` kimi düzgün göstərir.

`Skan: aktiv` rejimi açıq OlympTrade aktiv tabları arasında təxminən hər 15
saniyədə təhlükəsiz keçid edir və xam tick toplamağa çalışır. Bu keçid
`Yuxarı/Aşağı` düymələrinə toxunmur. Demo əməliyyatı açıq olduqda rotasiya
avtomatik dayanır. OlympTrade-də tab kimi açılmayan və platformanın məlumat
göndərmədiyi aktiv üçün `Canlı axın yoxdur` görünə bilər. İstənilən vaxt
paneldəki `Skan: aktiv` düyməsi ilə rotasiyanı dayandırmaq mümkündür.

## OpenAI inteqrasiyası

API açarı `outputs/.env.local` faylında `OPENAI_API_KEY` kimi saxlanılır. Bu fayl
ZIP paketinə daxil edilmir və açar paneldə/jurnalda göstərilmir.

Yerli çoxfaktorlu strategiya siqnal yaratdıqda bot son 25 tamamlanmış şamı,
indikatorları və təklif edilən istiqaməti OpenAI Responses API-yə göndərir.
OpenAI yeni istiqamət yaratmır; yalnız mövcud siqnalı əlavə olaraq təsdiqləyir
və ya rədd edir. Strukturlaşdırılmış cavabda təsdiq, 0–100% etibar, risk
səviyyəsi və qısa Azərbaycan dilində səbəb qaytarılır.

Əməliyyat yalnız aşağıdakı hallarda növbəyə düşür:

- yerli One Minute Trend v6 balı ən azı 75/100 olur;
- aktiv tarixi və son 30% backtest minimumlarını keçir;
- OpenAI cavabı siqnalı təsdiqləyir;
- etibar ən azı 65%-dir;
- risk səviyyəsi `HIGH` deyil;
- OlympTrade Demo hesabı, aktiv, məbləğ və müddət yoxlamaları keçir.

API əlçatan olmadıqda, açar etibarsız olduqda, kvota olmadıqda və ya cavab
formatı düzgün gəlmədikdə bot yalnız Demo hesabında təsdiqlənmiş yerli
One Minute Trend v6 qərarı ilə davam edir. Giriş vaxtı bitmiş siqnal heç vaxt
gecikmiş əməliyyata çevrilmir. OpenAI siqnalı açıq şəkildə rədd edərsə
əməliyyat yenə açılmır. OpenAI istifadəsi API hesabında ayrıca istifadəyə və
ödənişə səbəb ola bilər. Bu filtr və yerli strategiya qazanc təminatı vermir.

## Qrafik tarixçəsi

Bot OlympTrade səhifəsi açılarkən WebSocket-dən gələn OHLC obyektlərini, tarixi tick siyahılarını və `[timestamp, open, high, low, close]` şam formatlarını tanıyır. Platformanın həmin sessiyada brauzerə göndərdiyi tarixçə canlı şamlarla zaman üzrə birləşdirilir və dublikatlar silinir.

OlympTrade bütün mövcud tarixçəni deyil, yalnız qrafik üçün lazım olan məhdud aralığı göndərə bilər. Bot aldığı və sonradan canlı topladığı son 1.000 şamı hər aktiv üçün `runtime/data/olympbot_demo.sqlite3` bazasında saxlayır. Buna görə sonrakı açılışlarda əvvəlki bot sessiyalarının qrafiki dərhal görünür.

Panel ünvanı: `http://127.0.0.1:5000/`
