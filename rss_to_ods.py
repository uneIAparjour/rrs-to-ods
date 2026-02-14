#!/usr/bin/env python3
"""
rss_to_ods.py — Récupère le flux RSS complet (paginé) de uneiaparjour.fr
                 et génère un fichier ODS structuré.

Usage :
    python rss_to_ods.py                          # Flux par défaut + sortie par défaut
    python rss_to_ods.py -u https://example.com/feed/ -o mon_fichier.ods
    python rss_to_ods.py --max 50                  # Limiter à 50 articles
    python rss_to_ods.py --no-paginate             # Ne pas paginer (page 1 uniquement)
"""

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

import feedparser
from odf.opendocument import OpenDocumentSpreadsheet
from odf.style import Style, TableCellProperties, TableColumnProperties, TextProperties
from odf.table import Table, TableCell, TableColumn, TableRow
from odf.text import P

# ── Configuration par défaut ──────────────────────────────────────────────────
DEFAULT_FEED_URL = "https://www.uneiaparjour.fr/feed/"
DEFAULT_OUTPUT = "uneiaparjour.ods"
MAX_CATEGORIES = 6
DELAY_BETWEEN_PAGES = 1  # secondes entre chaque requête (politesse)

COLUMNS = [
    ("Titre", 8),
    ("Description", 16),
    ("URL sur uneiaparjour.fr", 10),
    ("Catégorie 1", 5),
    ("Catégorie 2", 5),
    ("Catégorie 3", 5),
    ("Catégorie 4", 5),
    ("Catégorie 5", 5),
    ("Catégorie 6", 5),
    ("Date de publication", 6),
]


# ── Helpers ───────────────────────────────────────────────────────────────────
def strip_html(html_text: str) -> str:
    """Supprime les balises HTML et décode les entités."""
    text = re.sub(r"<[^>]+>", "", html_text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def format_date(date_str: str) -> str:
    """Convertit une date RSS en format lisible JJ/MM/AAAA."""
    try:
        dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
        return dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return date_str or ""


def parse_pub_date(date_str: str) -> datetime | None:
    """Parse une date RSS en objet datetime pour comparaison."""
    try:
        return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
    except (ValueError, TypeError):
        return None


def parse_user_date(date_str: str) -> datetime:
    """Parse une date utilisateur JJ/MM/AAAA ou AAAA-MM-JJ."""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(
        f"Format de date invalide : '{date_str}'. "
        f"Utilisez JJ/MM/AAAA ou AAAA-MM-JJ."
    )


def build_paged_url(base_url: str, page: int) -> str:
    """Construit l'URL paginée pour un flux WordPress."""
    parsed = urlparse(base_url)
    params = parse_qs(parsed.query)
    params["paged"] = [str(page)]
    new_query = urlencode(params, doseq=True)
    return parsed._replace(query=new_query).geturl()


def fetch_all_entries(url: str, paginate: bool = True, max_items: int | None = None,
                      delay: float = 1.0) -> list:
    """
    Récupère tous les articles du flux RSS en paginant automatiquement.
    WordPress expose /feed/?paged=1, ?paged=2, etc.
    La pagination s'arrête quand une page ne retourne aucun article
    ou retourne une erreur (404).
    """
    all_entries = []
    page = 1
    seen_links = set()

    while True:
        paged_url = build_paged_url(url, page) if paginate and page > 1 else url
        print(f"📡 Page {page} : {paged_url}")

        feed = feedparser.parse(paged_url)

        # Détection de fin : erreur de parsing sans entrées
        if feed.bozo and not feed.entries:
            if page == 1:
                print(f"❌ Erreur lors du parsing : {feed.bozo_exception}", file=sys.stderr)
                sys.exit(1)
            else:
                print(f"   → Fin de la pagination (page {page} inaccessible)")
                break

        # Détection de fin : page vide
        if not feed.entries:
            print(f"   → Fin de la pagination (page {page} vide)")
            break

        # Détection de fin : HTTP 404 ou redirection vers page d'erreur
        if hasattr(feed, "status") and feed.status == 404:
            print(f"   → Fin de la pagination (404)")
            break

        new_count = 0
        for entry in feed.entries:
            link = entry.get("link", "")
            if link not in seen_links:
                seen_links.add(link)
                all_entries.append(entry)
                new_count += 1

        print(f"   → {new_count} nouveaux articles (total : {len(all_entries)})")

        # Aucun nouvel article → doublons = fin
        if new_count == 0:
            print(f"   → Fin de la pagination (doublons détectés)")
            break

        # Limite atteinte
        if max_items and len(all_entries) >= max_items:
            all_entries = all_entries[:max_items]
            print(f"   → Limite de {max_items} articles atteinte")
            break

        if not paginate:
            break

        page += 1
        time.sleep(delay)

    return all_entries


def parse_entries(entries: list, date_from: datetime | None = None,
                  date_to: datetime | None = None) -> list[dict]:
    """Transforme les entrées feedparser en lignes structurées, avec filtre par date."""
    rows = []
    skipped = 0
    for entry in entries:
        # Filtrage par date
        if date_from or date_to:
            pub = parse_pub_date(entry.get("published", ""))
            if pub:
                if date_from and pub < date_from:
                    skipped += 1
                    continue
                if date_to and pub > date_to.replace(hour=23, minute=59, second=59):
                    skipped += 1
                    continue

        categories = [tag.term for tag in getattr(entry, "tags", [])]
        cats = (categories + [""] * MAX_CATEGORIES)[:MAX_CATEGORIES]

        rows.append({
            "titre": entry.get("title", ""),
            "description": strip_html(
                entry.get("description", "") or entry.get("summary", "")
            ),
            "url": entry.get("link", ""),
            "categories": cats,
            "date": format_date(entry.get("published", "")),
        })

    if skipped:
        print(f"📅 {skipped} articles hors de la plage de dates (ignorés)")

    return rows


# ── Génération ODS ────────────────────────────────────────────────────────────
def create_ods(rows: list[dict], output_path: str) -> None:
    """Crée le fichier ODS avec mise en forme professionnelle."""
    doc = OpenDocumentSpreadsheet()

    # — Styles —
    header_style = Style(name="HeaderCell", family="table-cell")
    header_style.addElement(TableCellProperties(
        backgroundcolor="#2C3E50", padding="0.15cm"
    ))
    header_style.addElement(TextProperties(
        fontsize="11pt", fontweight="bold", color="#FFFFFF", fontfamily="Arial"
    ))
    doc.automaticstyles.addElement(header_style)

    cell_style = Style(name="DataCell", family="table-cell")
    cell_style.addElement(TableCellProperties(
        padding="0.1cm", borderbottom="0.5pt solid #DEE2E6"
    ))
    cell_style.addElement(TextProperties(fontsize="10pt", fontfamily="Arial"))
    doc.automaticstyles.addElement(cell_style)

    cat_style = Style(name="CatCell", family="table-cell")
    cat_style.addElement(TableCellProperties(
        backgroundcolor="#F0F4F8", padding="0.1cm",
        borderbottom="0.5pt solid #DEE2E6"
    ))
    cat_style.addElement(TextProperties(fontsize="10pt", fontfamily="Arial"))
    doc.automaticstyles.addElement(cat_style)

    even_style = Style(name="EvenCell", family="table-cell")
    even_style.addElement(TableCellProperties(
        backgroundcolor="#F9FAFB", padding="0.1cm",
        borderbottom="0.5pt solid #DEE2E6"
    ))
    even_style.addElement(TextProperties(fontsize="10pt", fontfamily="Arial"))
    doc.automaticstyles.addElement(even_style)

    even_cat_style = Style(name="EvenCatCell", family="table-cell")
    even_cat_style.addElement(TableCellProperties(
        backgroundcolor="#EEF1F5", padding="0.1cm",
        borderbottom="0.5pt solid #DEE2E6"
    ))
    even_cat_style.addElement(TextProperties(fontsize="10pt", fontfamily="Arial"))
    doc.automaticstyles.addElement(even_cat_style)

    col_styles = []
    for i, (_, width_cm) in enumerate(COLUMNS):
        cs = Style(name=f"Col{i}", family="table-column")
        cs.addElement(TableColumnProperties(columnwidth=f"{width_cm}cm"))
        doc.automaticstyles.addElement(cs)
        col_styles.append(cs)

    # — Table —
    table = Table(name="Articles")

    for cs in col_styles:
        table.addElement(TableColumn(stylename=cs))

    # En-tête
    header_row = TableRow()
    for col_name, _ in COLUMNS:
        cell = TableCell(stylename=header_style)
        cell.addElement(P(text=col_name))
        header_row.addElement(cell)
    table.addElement(header_row)

    # Données
    for idx, row in enumerate(rows):
        tr = TableRow()
        is_even = idx % 2 == 1
        cs = even_style if is_even else cell_style
        ccs = even_cat_style if is_even else cat_style

        for value, style in [
            (row["titre"], cs),
            (row["description"], cs),
            (row["url"], cs),
        ]:
            tc = TableCell(stylename=style)
            tc.addElement(P(text=value))
            tr.addElement(tc)

        for cat in row["categories"]:
            tc = TableCell(stylename=ccs)
            tc.addElement(P(text=cat))
            tr.addElement(tc)

        tc = TableCell(stylename=cs)
        tc.addElement(P(text=row["date"]))
        tr.addElement(tc)

        table.addElement(tr)

    doc.spreadsheet.addElement(table)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    print(f"\n✅ Fichier généré : {output_path}")
    print(f"   📊 {len(rows)} articles — 10 colonnes — {MAX_CATEGORIES} catégories max")


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Convertit un flux RSS WordPress (paginé) en fichier ODS."
    )
    parser.add_argument(
        "-u", "--url",
        default=DEFAULT_FEED_URL,
        help=f"URL du flux RSS (défaut : {DEFAULT_FEED_URL})"
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT,
        help=f"Chemin du fichier ODS de sortie (défaut : {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Nombre maximum d'articles à traiter"
    )
    parser.add_argument(
        "--no-paginate",
        action="store_true",
        help="Ne pas paginer (première page uniquement)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DELAY_BETWEEN_PAGES,
        help=f"Délai entre les pages en secondes (défaut : {DELAY_BETWEEN_PAGES})"
    )
    parser.add_argument(
        "--from", dest="date_from",
        type=str, default=None,
        help="Date de début (JJ/MM/AAAA ou AAAA-MM-JJ). Ex : 25/04/2025"
    )
    parser.add_argument(
        "--to", dest="date_to",
        type=str, default=None,
        help="Date de fin (JJ/MM/AAAA ou AAAA-MM-JJ). Ex : 14/02/2026"
    )
    args = parser.parse_args()

    # Parsing des dates
    date_from = parse_user_date(args.date_from) if args.date_from else None
    date_to = parse_user_date(args.date_to) if args.date_to else None

    if date_from and date_to and date_from > date_to:
        print("❌ La date --from doit être antérieure à --to.", file=sys.stderr)
        sys.exit(1)

    if date_from or date_to:
        f = date_from.strftime("%d/%m/%Y") if date_from else "…"
        t = date_to.strftime("%d/%m/%Y") if date_to else "…"
        print(f"📅 Filtre : du {f} au {t}")

    entries = fetch_all_entries(
        args.url,
        paginate=not args.no_paginate,
        max_items=args.max,
        delay=args.delay,
    )

    if not entries:
        print("⚠️  Aucun article trouvé dans le flux.", file=sys.stderr)
        sys.exit(1)

    print(f"\n📰 Total : {len(entries)} articles récupérés")

    rows = parse_entries(entries, date_from=date_from, date_to=date_to)
    create_ods(rows, args.output)


if __name__ == "__main__":
    main()
