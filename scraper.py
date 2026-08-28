import asyncio
import json
import os
import re
import smtplib
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import urljoin, urlsplit, urlunsplit

from playwright.async_api import async_playwright


# ============================================================
# CONFIGURATION
# ============================================================

ARBEITSAGENTUR_URL = (
    "https://www.arbeitsagentur.de/jobsuche/"
    "suche?suchbereich=ausbildung"
    "&veroeffentlichtseit=0"
    "&was=Verk%C3%A4ufer%2Fin"
)

BASE_URL = "https://www.arbeitsagentur.de"

EMAIL_TO = "amine.bouafia1998@gmail.com"

EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

DATABASE_FILE = "data.json"


# ============================================================
# BASE DE DONNÉES
# ============================================================

def load_database():

    if not os.path.exists(DATABASE_FILE):
        return []

    try:

        with open(
            DATABASE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

            if isinstance(data, list):
                return data

            return []

    except Exception as error:

        print(
            "⚠️ Erreur lecture database :",
            error
        )

        return []


def save_database(database):

    with open(
        DATABASE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            database,
            file,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# NORMALISATION URL
# ============================================================

def normalize_url(url):

    if not url:
        return ""

    url = url.strip()

    if url.startswith("/"):
        url = urljoin(
            BASE_URL,
            url
        )

    try:

        parts = urlsplit(url)

        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path.rstrip("/"),
                parts.query,
                ""
            )
        )

    except Exception:

        return url


# ============================================================
# EXTRACTION EMAIL
# ============================================================

def extract_email(text):

    if not text:
        return ""

    pattern = (
        r"[A-Za-z0-9._%+-]+"
        r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    )

    emails = re.findall(
        pattern,
        text
    )

    ignored = {
        "example@example.com",
        "noreply@arbeitsagentur.de",
        "no-reply@arbeitsagentur.de"
    }

    for email in emails:

        email = email.strip().lower()

        if email not in ignored:
            return email

    return ""


# ============================================================
# EXTRACTION TELEPHONE
# ============================================================

def extract_phone(text):

    if not text:
        return ""

    patterns = [

        r"\+49[\s./()-]*\d(?:[\s./()-]*\d){6,15}",

        r"0049[\s./()-]*\d(?:[\s./()-]*\d){6,15}",

        r"0\d{2,5}[\s./()-]*\d{3,10}"

    ]

    for pattern in patterns:

        phones = re.findall(
            pattern,
            text
        )

        if phones:

            return phones[0].strip()

    return ""


# ============================================================
# OUVRIR ARBEITSAGENTUR
# ============================================================

async def open_jobs_page(page):

    print(
        "🌐 Ouverture de Arbeitsagentur..."
    )

    await page.goto(
        ARBEITSAGENTUR_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    await page.wait_for_timeout(
        8000
    )

    print(
        "✅ Jobsuche chargée"
    )


# ============================================================
# CHARGER TOUTES LES OFFRES
# ============================================================

async def load_all_results(page):

    print(
        "📄 Chargement de toutes les offres..."
    )

    clicks = 0

    while True:

        try:

            buttons = page.get_by_text(
                "Weitere Ergebnisse",
                exact=True
            )

            count = await buttons.count()

            if count == 0:

                print(
                    "✅ Toutes les offres sont chargées."
                )

                break

            button = buttons.last

            await button.scroll_into_view_if_needed()

            await page.wait_for_timeout(
                1000
            )

            await button.click()

            clicks += 1

            print(
                f"➡️ Chargement supplémentaire #{clicks}"
            )

            await page.wait_for_timeout(
                4000
            )

            if clicks >= 100:

                print(
                    "⚠️ Limite de sécurité atteinte."
                )

                break

        except Exception as error:

            print(
                "⚠️ Fin du chargement :",
                error
            )

            break


# ============================================================
# RECUPERER LES OFFRES
# ============================================================

async def collect_jobs(page):

    print(
        "🔎 Recherche de toutes les offres "
        "Ausbildung Verkäufer/in..."
    )

    jobs = []

    seen_urls = set()

    try:

        await page.wait_for_selector(
            "a",
            timeout=30000
        )

    except Exception:

        print(
            "⚠️ Aucun résultat détecté."
        )

        return jobs

    await load_all_results(
        page
    )

    links = await page.locator(
        "a"
    ).all()

    print(
        f"🔗 {len(links)} liens analysés."
    )

    for link in links:

        try:

            title = (
                await link.inner_text()
            ).strip()

            href = await link.get_attribute(
                "href"
            )

            if not title or not href:
                continue

            title_lower = title.lower()

            if (
                "verkäufer" not in title_lower
                and "verkäuferin" not in title_lower
            ):
                continue

            href = normalize_url(
                href
            )

            if not href.startswith(
                "http"
            ):
                continue

            if href in seen_urls:
                continue

            seen_urls.add(
                href
            )

            jobs.append(
                {
                    "title": title,
                    "url": href,
                    "company": "",
                    "city": "",
                    "email": "",
                    "phone": "",
                    "bewerbung_info": "",
                    "date": datetime.now().strftime(
                        "%Y-%m-%d"
                    )
                }
            )

        except Exception:

            continue

    print(
        f"📊 TOTAL OFFRES TROUVÉES : "
        f"{len(jobs)}"
    )

    return jobs


# ============================================================
# EXTRAIRE INFORMATIONEN ZUR BEWERBUNG
# ============================================================

def extract_bewerbung_info(text):

    if not text:
        return ""

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    start_index = None

    # Chercher la section exacte
    for i, line in enumerate(lines):

        normalized = (
            line.lower()
            .replace(":", "")
            .strip()
        )

        if (
            "informationen zur bewerbung"
            in normalized
        ):

            start_index = i

            break

    if start_index is None:

        return ""

    information = []

    for line in lines[
        start_index + 1:
    ]:

        lower = line.lower()

        # Nouvelle section
        if (
            lower.startswith("aufgaben")
            or lower.startswith("anforderungen")
            or lower.startswith("profil")
            or lower.startswith("angebot")
            or lower.startswith("über uns")
            or lower.startswith("wir bieten")
            or lower.startswith("sonstiges")
            or lower.startswith("stellenbeschreibung")
        ):

            break

        information.append(
            line
        )

        if len(information) >= 40:

            break

    return "\n".join(
        information
    ).strip()


# ============================================================
# EXTRAIRE ENTREPRISE
# ============================================================

def extract_company(lines):

    # Priorité à Arbeitgeber
    for i, line in enumerate(lines):

        lower = line.lower()

        if (
            lower == "arbeitgeber"
            or lower == "arbeitgeber:"
        ):

            if i + 1 < len(lines):

                company = (
                    lines[i + 1].strip()
                )

                if company:

                    return company

    # Ensuite Unternehmen
    for i, line in enumerate(lines):

        lower = line.lower()

        if (
            lower == "unternehmen"
            or lower == "unternehmen:"
        ):

            if i + 1 < len(lines):

                company = (
                    lines[i + 1].strip()
                )

                if company:

                    return company

    # Enfin Firma
    for i, line in enumerate(lines):

        lower = line.lower()

        if (
            lower == "firma"
            or lower == "firma:"
        ):

            if i + 1 < len(lines):

                company = (
                    lines[i + 1].strip()
                )

                if company:

                    return company

    return ""


# ============================================================
# EXTRAIRE VILLE
# ============================================================

def extract_city(lines):

    for i, line in enumerate(lines):

        lower = line.lower()

        if lower in [
            "arbeitsort",
            "arbeitsort:",
            "ort",
            "standort",
            "standort:"
        ]:

            if i + 1 < len(lines):

                city = (
                    lines[i + 1].strip()
                )

                if city:

                    return city

    return ""


# ============================================================
# ANALYSER UNE OFFRE
# ============================================================

async def scrape_job_details(
    browser,
    job
):

    page = await browser.new_page()

    try:

        print(
            "➡️ Analyse :",
            job["title"]
        )

        await page.goto(
            job["url"],
            wait_until="domcontentloaded",
            timeout=60000
        )

        await page.wait_for_timeout(
            4000
        )

        text = await page.locator(
            "body"
        ).inner_text()

        lower_text = text.lower()

        # ====================================================
        # CAPTCHA
        # ====================================================

        captcha_detected = (

            "captcha" in lower_text

            or
            "sicherheitsüberprüfung"
            in lower_text

            or
            "verify you are human"
            in lower_text

            or
            "ich bin kein roboter"
            in lower_text

        )

        if captcha_detected:

            print(
                "⚠️ CAPTCHA détecté → OFFRE IGNORÉE"
            )

            return None

        # ====================================================
        # LIGNES
        # ====================================================

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        # ====================================================
        # INFORMATIONEN ZUR BEWERBUNG
        # ====================================================

        bewerbung_info = (
            extract_bewerbung_info(
                text
            )
        )

        if not bewerbung_info:

            print(
                "⏭️ Informationen zur Bewerbung "
                "absentes → OFFRE IGNORÉE"
            )

            return None

        job["bewerbung_info"] = (
            bewerbung_info
        )

        # ====================================================
        # EMAIL UNIQUEMENT DE LA SECTION
        # ====================================================

        email = extract_email(
            bewerbung_info
        )

        if not email:

            print(
                "⏭️ Email absent de "
                "Informationen zur Bewerbung "
                "→ OFFRE IGNORÉE"
            )

            return None

        job["email"] = email

        # ====================================================
        # TELEPHONE UNIQUEMENT DE LA SECTION
        # ====================================================

        phone = extract_phone(
            bewerbung_info
        )

        if not phone:

            print(
                "⏭️ Téléphone absent de "
                "Informationen zur Bewerbung "
                "→ OFFRE IGNORÉE"
            )

            return None

        job["phone"] = phone

        # ====================================================
        # ENTREPRISE
        # ====================================================

        company = extract_company(
            lines
        )

        if not company:

            print(
                "⏭️ Entreprise non trouvée "
                "→ OFFRE IGNORÉE"
            )

            return None

        job["company"] = company

        # ====================================================
        # VILLE
        # ====================================================

        job["city"] = extract_city(
            lines
        )

        # ====================================================
        # VALIDATION FINALE
        # ====================================================

        if (
            not job["company"]
            or not job["email"]
            or not job["phone"]
            or not job["bewerbung_info"]
        ):

            print(
                "⏭️ Offre incomplète → IGNORÉE"
            )

            return None

        print(
            "✅ OFFRE ACCEPTÉE :",
            job["company"],
            "|",
            job["email"],
            "|",
            job["phone"]
        )

        return job

    except Exception as error:

        print(
            "⚠️ Erreur analyse offre :",
            error
        )

        return None

    finally:

        await page.close()


# ============================================================
# TRAITER LES OFFRES
# ============================================================

async def process_jobs(
    jobs,
    database
):

    new_jobs = []

    existing_urls = {
        normalize_url(
            job.get("url", "")
        )
        for job in database
        if job.get("url")
    }

    print(
        f"🗄️ Offres déjà enregistrées : "
        f"{len(existing_urls)}"
    )

    # ========================================================
    # DÉDUPLICATION
    # ========================================================

    unique_jobs = []

    seen_urls = set()

    for job in jobs:

        url = normalize_url(
            job.get("url", "")
        )

        if not url:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(
            url
        )

        job["url"] = url

        unique_jobs.append(
            job
        )

    print(
        f"🧹 Après suppression des doublons : "
        f"{len(unique_jobs)}"
    )

    # ========================================================
    # ANALYSE
    # ========================================================

    async with async_playwright() as playwright:

        browser = await playwright.chromium.launch(
            headless=True
        )

        for index, job in enumerate(
            unique_jobs,
            start=1
        ):

            if job["url"] in existing_urls:

                print(
                    f"⏭️ [{index}/{len(unique_jobs)}] "
                    "Déjà envoyée :",
                    job["title"]
                )

                continue

            print(
                f"🔎 [{index}/{len(unique_jobs)}]"
            )

            result = await scrape_job_details(
                browser,
                job
            )

            # =================================================
            # OFFRE VALIDE
            # =================================================

            if result is not None:

                new_jobs.append(
                    result
                )

                database.append(
                    result
                )

                existing_urls.add(
                    result["url"]
                )

            # =================================================
            # OFFRE IGNORÉE
            # =================================================

            else:

                print(
                    "🚫 Offre non conforme "
                    "→ pas de sauvegarde"
                )

            await asyncio.sleep(
                0.5
            )

        await browser.close()

    return new_jobs


# ============================================================
# CREER EMAIL
# ============================================================

def create_email(jobs):

    today = datetime.now().strftime(
        "%d/%m/%Y"
    )

    html = f"""
    <html>
    <body>

    <h2>
    🇩🇪 Ausbildung Verkäufer/in
    </h2>

    <p>
    📅 Date :
    <b>{today}</b>
    </p>

    <p>
    📊 Nouvelles offres avec
    Informationen zur Bewerbung :
    <b>{len(jobs)}</b>
    </p>

    <hr>
    """

    if not jobs:

        html += """
        <p>
        Aucune nouvelle offre correspondant
        aux critères aujourd'hui.
        </p>
        """

    else:

        for number, job in enumerate(
            jobs,
            start=1
        ):

            title = job.get(
                "title",
                "Sans titre"
            )

            company = job.get(
                "company",
                ""
            )

            city = job.get(
                "city",
                ""
            )

            email = job.get(
                "email",
                ""
            )

            phone = job.get(
                "phone",
                ""
            )

            bewerbung_info = job.get(
                "bewerbung_info",
                ""
            )

            url = job.get(
                "url",
                ""
            )

            bewerbung_html = (
                bewerbung_info
                .replace(
                    "\n",
                    "<br>"
                )
            )

            html += f"""

            <h3>
            {number}. {title}
            </h3>

            <p>
            🏢 <b>Entreprise :</b>
            {company}
            </p>

            <p>
            📍 <b>Ville :</b>
            {city or "Non trouvée"}
            </p>

            <p>
            📧 <b>Email :</b>
            {email}
            </p>

            <p>
            ☎️ <b>Téléphone :</b>
            {phone}
            </p>

            <p>
            📋 <b>Informationen zur Bewerbung :</b>
            </p>

            <div>
            {bewerbung_html}
            </div>

            <p>
            🔗
            <a href="{url}">
            Voir l'offre sur Arbeitsagentur
            </a>
            </p>

            <hr>
            """

    html += """

    <p>
    🤖 Rapport automatique
    </p>

    </body>
    </html>
    """

    return html


# ============================================================
# ENVOYER EMAIL
# ============================================================

def send_email(jobs):

    today = datetime.now().strftime(
        "%d/%m/%Y"
    )

    message = EmailMessage()

    message["Subject"] = (
        "🇩🇪 Ausbildung Verkäufer/in - "
        f"{len(jobs)} nouvelles offres - "
        f"{today}"
    )

    message["From"] = EMAIL_FROM

    message["To"] = EMAIL_TO

    message.add_alternative(
        create_email(jobs),
        subtype="html"
    )

    print(
        "📧 Envoi du rapport..."
    )

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465
    ) as smtp:

        smtp.login(
            EMAIL_FROM,
            EMAIL_PASSWORD
        )

        smtp.send_message(
            message
        )

    print(
        "✅ Email envoyé à",
        EMAIL_TO
    )


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

async def main():

    print("=" * 60)

    print(
        "🇩🇪 AUSBILDUNG VERKÄUFER BOT"
    )

    print(
        "🎯 FILTRE : INFORMATIONEN ZUR BEWERBUNG"
    )

    print("=" * 60)

    database = load_database()

    print(
        f"🗄️ Base actuelle : "
        f"{len(database)} offres"
    )

    # ========================================================
    # RECHERCHE
    # ========================================================

    async with async_playwright() as playwright:

        browser = await playwright.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        try:

            await open_jobs_page(
                page
            )

            jobs = await collect_jobs(
                page
            )

        finally:

            await page.close()

            await browser.close()

    # ========================================================
    # TRAITEMENT
    # ========================================================

    new_jobs = await process_jobs(
        jobs,
        database
    )

    # ========================================================
    # SAUVEGARDE
    # ========================================================

    save_database(
        database
    )

    print("=" * 60)

    print(
        f"🔎 OFFRES TROUVÉES : "
        f"{len(jobs)}"
    )

    print(
        f"🆕 OFFRES ACCEPTÉES : "
        f"{len(new_jobs)}"
    )

    print(
        f"📚 TOTAL BASE : "
        f"{len(database)}"
    )

    print("=" * 60)

    # ========================================================
    # EMAIL
    # ========================================================

    send_email(
        new_jobs
    )

    print("=" * 60)

    print(
        "✅ TERMINÉ"
    )

    print("=" * 60)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
