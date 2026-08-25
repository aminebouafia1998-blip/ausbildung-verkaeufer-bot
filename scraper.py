import asyncio
import json
import os
import re
import smtplib
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import urljoin

from playwright.async_api import async_playwright


# ============================================================
# CONFIGURATION
# ============================================================

ARBEITSAGENTUR_URL = (
    "https://www.arbeitsagentur.de/jobsuche/"
    "suche?suchbereich=ausbildung&was=Verk%C3%A4ufer%2Fin"
)

EMAIL_TO = "zimcotter@gmail.com"

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
        with open(DATABASE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    except Exception:
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
# EXTRACTION EMAIL
# ============================================================

def extract_email(text):

    pattern = (
        r"[A-Za-z0-9._%+-]+"
        r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    )

    emails = re.findall(pattern, text)

    if emails:
        return emails[0]

    return ""


# ============================================================
# EXTRACTION TELEPHONE
# ============================================================

def extract_phone(text):

    pattern = (
        r"(?:"
        r"\+49"
        r"|0049"
        r"|0"
        r")"
        r"[\s./()-]*"
        r"\d"
        r"(?:[\s./()-]*\d){6,15}"
    )

    phones = re.findall(pattern, text)

    if phones:
        return phones[0].strip()

    return ""


# ============================================================
# OUVRIR ARBEITSAGENTUR
# ============================================================

async def open_jobs_page(page):

    print("🌐 Ouverture de Arbeitsagentur...")

    await page.goto(
        ARBEITSAGENTUR_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    await page.wait_for_timeout(8000)

    print("✅ Jobsuche chargée")


# ============================================================
# RECUPERER LES OFFRES
# ============================================================

async def collect_jobs(page):

    print("🔎 Recherche des offres Verkäufer/in...")

    jobs = []

    try:

        await page.wait_for_selector(
            "a",
            timeout=30000
        )

    except Exception:

        print("⚠️ Aucun résultat détecté.")

        return jobs


    links = await page.locator("a").all()

    for link in links:

        try:

            title = await link.inner_text()

            title = title.strip()

            href = await link.get_attribute("href")

            if not title or not href:
                continue

            if (
                "Verkäufer" not in title
                and "Verkäuferin" not in title
            ):
                continue

            if href.startswith("/"):

                href = urljoin(
                    "https://www.arbeitsagentur.de",
                    href
                )

            if not href.startswith("http"):
                continue

            if any(
                job["url"] == href
                for job in jobs
            ):
                continue

            jobs.append({
                "title": title,
                "url": href,
                "company": "",
                "city": "",
                "email": "",
                "phone": "",
                "date": datetime.now().strftime("%Y-%m-%d")
            })

        except Exception:

            continue


    print(
        f"📊 {len(jobs)} offres trouvées"
    )

    return jobs


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

        await page.wait_for_timeout(4000)

        text = await page.locator(
            "body"
        ).inner_text()

        # EMAIL
        job["email"] = extract_email(text)

        # TELEPHONE
        job["phone"] = extract_phone(text)

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        # VILLE
        for i, line in enumerate(lines):

            if line.lower() in [
                "arbeitsort",
                "arbeitsort:",
                "ort",
                "standort"
            ]:

                if i + 1 < len(lines):

                    job["city"] = lines[i + 1]

                    break

        # ENTREPRISE
        for i, line in enumerate(lines):

            lower = line.lower()

            if (
                "arbeitgeber" in lower
                or "unternehmen" in lower
                or "firma" in lower
            ):

                if i + 1 < len(lines):

                    job["company"] = lines[i + 1]

                    break

    except Exception as error:

        print(
            "⚠️ Erreur :",
            error
        )

    finally:

        await page.close()

    return job


# ============================================================
# TRAITER LES OFFRES
# ============================================================

async def process_jobs(jobs, database):

    new_jobs = []

    existing_urls = {
        job.get("url")
        for job in database
    }

    async with async_playwright() as playwright:

        browser = await playwright.chromium.launch(
            headless=True
        )

        for job in jobs:

            if job["url"] in existing_urls:

                print(
                    "⏭️ Déjà enregistrée :",
                    job["title"]
                )

                continue

            job = await scrape_job_details(
                browser,
                job
            )

            new_jobs.append(job)

            database.append(job)

            await asyncio.sleep(1)

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

    <h2>🇩🇪 Nouvelles Ausbildung Verkäufer/in</h2>

    <p>
    📅 Date : <b>{today}</b>
    </p>

    <p>
    📊 Nouvelles offres :
    <b>{len(jobs)}</b>
    </p>

    <hr>
    """

    if not jobs:

        html += """
        <p>
        Aucune nouvelle offre trouvée aujourd'hui.
        </p>
        """

    else:

        for number, job in enumerate(
            jobs,
            start=1
        ):

            html += f"""

            <h3>
            {number}. {job["title"]}
            </h3>

            <p>
            🏢 <b>Entreprise :</b>
            {job["company"] or "Non trouvé"}
            </p>

            <p>
            📍 <b>Ville :</b>
            {job["city"] or "Non trouvée"}
            </p>

            <p>
            📧 <b>Email :</b>
            {job["email"] or "Non trouvé"}
            </p>

            <p>
            ☎️ <b>Téléphone :</b>
            {job["phone"] or "Non trouvé"}
            </p>

            <p>
            🔗
            <a href="{job["url"]}">
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
        f"{len(jobs)} nouvelles offres - {today}"
    )

    message["From"] = EMAIL_FROM
    message["To"] = EMAIL_TO

    html = create_email(jobs)

    message.add_alternative(
        html,
        subtype="html"
    )

    print("📧 Envoi du rapport...")

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465
    ) as smtp:

        smtp.login(
            EMAIL_FROM,
            EMAIL_PASSWORD
        )

        smtp.send_message(message)

    print(
        "✅ Email envoyé à",
        EMAIL_TO
    )


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

async def main():

    print("=" * 60)

    print("🇩🇪 AUSBILDUNG VERKÄUFER BOT")

    print("=" * 60)

    database = load_database()

    async with async_playwright() as playwright:

        browser = await playwright.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        try:

            await open_jobs_page(page)

            jobs = await collect_jobs(page)

        finally:

            await page.close()

            await browser.close()


    new_jobs = await process_jobs(
        jobs,
        database
    )

    save_database(database)

    print(
        f"🆕 Nouvelles offres : {len(new_jobs)}"
    )

    send_email(new_jobs)

    print("=" * 60)

    print("✅ TERMINÉ")

    print("=" * 60)


if __name__ == "__main__":

    asyncio.run(main())
