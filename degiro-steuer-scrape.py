import pdfplumber
import pandas as pd
import re
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_text_from_pdf(pdf_path):
    """
    Extracts raw text from all pages of the PDF.
    """
    all_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                all_text += page.extract_text() or ""
        return all_text
    except Exception as e:
        logging.error(f"Error reading PDF: {e}")
        return ""


def extract_dividend_table(text):
    """
    Extracts the dividend table from the raw PDF text.
    Returns a DataFrame with dividend data.
    """
    try:
        pattern = re.compile(r"Land Bruttodividende Quellensteuer Nettodividende\n(.*?)\nKuponübersicht", re.S)
        dividend_match = pattern.search(text)
        
        if not dividend_match:
            logging.warning("Dividend table not found in text.")
            return pd.DataFrame()
        
        table_text = dividend_match.group(1).strip()
        divi_lines = table_text.split("\n")
        divi_data = [re.split(r'\s+', line) for line in divi_lines[:-1]]
        
        dividend_df = pd.DataFrame(divi_data, columns=["Land", "Bruttodividende", "Quellensteuer", "Nettodividende"])
        
        # Clean and convert to float
        for col in ["Bruttodividende", "Quellensteuer", "Nettodividende"]:
            dividend_df[col] = dividend_df[col].str.replace(',', '.').astype(float)
        
        dividend_df["Steuersatz"] = dividend_df["Quellensteuer"] / dividend_df["Bruttodividende"]

        dividend_sum = dividend_df["Bruttodividende"].sum()
        dividend_sum_de = dividend_df.loc[dividend_df["Land"] == "DE", "Bruttodividende"].sum()
        dividend_sum_ausl = dividend_df.loc[dividend_df["Land"] != "DE", "Bruttodividende"].sum()


        return dividend_df, dividend_sum, dividend_sum_de, dividend_sum_ausl

    except Exception as e:
        logging.error(f"Error extracting dividend table: {e}")
        return pd.DataFrame()
    


def extract_realized_profits_and_fees(raw_text):
    # Regex für den Abschnitt der realisierten Gewinne/Verluste
    section_pattern = r"(Realisierte Gewinne/Verluste je Produkt)(.*?)(Alle Dividenden und Kupons)"
    section_match = re.search(section_pattern, raw_text, re.DOTALL)
    
    if not section_match:
        return None
    
    # Extrahierte Tabelle
    section_text = section_match.group(2)
    
    # Regex für die eigentlichen Daten (Produkt, ISIN, Gewinne/Verluste, Gebühr)
    table_pattern = r"([A-Za-z0-9\s&\.\-]+)\s+([A-Z0-9]+)\s+([\-0-9,\.]+)\s+([\-0-9,\.]+)"
    
    # Extrahieren der Tabellenzeilen
    rows = re.findall(table_pattern, section_text)
    
    # Erstellen einer Liste von Dictionaries für jedes Produkt
    data = []
    for row in rows:
        isin = row[1].strip()
        data.append({
            "Produkt": row[0].strip(),
            "ISIN": isin,
            "Realisierte Gewinne/Verluste": row[2].strip(),
            "Transaktionsgebühr": row[3].strip(),
            "Land": isin[:2]
        })
    numeric_cols = ["Realisierte Gewinne/Verluste", "Transaktionsgebühr"]
    df = pd.DataFrame(data)
    for col in numeric_cols:
        df[col] = df[col].str.replace(',', '.').astype(float)
    
    df["G/V"] = df["Realisierte Gewinne/Verluste"] - df["Transaktionsgebühr"]

    positive_entries = df[df['G/V'] > 0]['G/V'].sum()
    negative_entries = df[df['G/V'] < 0]['G/V'].sum()

    positive_entries_de = df[(df['G/V'] > 0) & (df["Land"] == "DE")]['G/V'].sum()

    negative_entries_de = df[(df['G/V'] < 0) & (df["Land"] == "DE")]['G/V'].sum()

    positive_entries_ausl = df[(df['G/V'] > 0) & (df["Land"] != "DE")]['G/V'].sum()
    negative_entries_ausl = df[(df['G/V'] < 0) & (df["Land"] != "DE")]['G/V'].sum()


    return df, positive_entries, negative_entries, positive_entries_de, negative_entries_de, positive_entries_ausl, negative_entries_ausl


def extract_general_data(text):
    """
    Extracts general key-value pairs (like Ausschüttungen) from the PDF text.
    """
    data = []
    try:
        lines = text.split('\n')
        for line in lines:
            matches = re.findall(r'(.*?) (\d+,\d{2} EUR)', line)
            if matches:
                for description, value in matches:
                    data.append([description.strip(), value.strip()])
        return data
    except Exception as e:
        logging.error(f"Error extracting general data: {e}")
        return []


def save_to_excel(data, output_path):
    try:
        data.to_excel(output_path, index=False)
        logging.info(f"Data successfully saved to {output_path}")
    except Exception as e:
        logging.error(f"Failed to save Excel file: {e}")

        import re

import re

def extract_transaction_fee(raw_text):
    match = re.search(r"Transaktionsgebühren.*?([\d,.]+)\s*EUR", raw_text)
    
    if match:
        # Komma durch Punkt ersetzen und in float umwandeln
        fee = float(match.group(1).replace(',', '.'))
        return abs(fee)  # Immer negativ zurückgeben
    else:
        return 0  # 0 zurückgeben, falls keine Gebühr gefunden wird



def main(pdf_path, output_path):
    raw_text = extract_text_from_pdf(pdf_path)

    anlage_kap = pd.DataFrame()
    
    if not raw_text:
        logging.error("No text extracted from PDF.")
        return
    
    transaktionsgebuehren = extract_transaction_fee(raw_text)
    
    dividend_df, dividend_sum, dividend_sum_de, dividend_sum_ausl = extract_dividend_table(raw_text)
    profits_df, positive_entries, negative_entries, positive_entries_de, negative_entries_de, positive_entries_ausl, negative_entries_ausl = extract_realized_profits_and_fees(raw_text)

    kapitalertraege = dividend_sum_de + positive_entries_de

    kapitalertraege_ausl = positive_entries_ausl + negative_entries_ausl + dividend_sum_ausl + positive_entries_ausl - transaktionsgebuehren

    kapitalertraege_de = positive_entries_de + negative_entries_de + dividend_sum_de


    kapitalertragsteuer_divi = dividend_df.loc[dividend_df["Land"] == "DE"]["Quellensteuer"].sum()
    soli_divi = kapitalertragsteuer_divi * 0.055
    anrechenb_ausl_steuer = dividend_sum_ausl * 0.15

    tax_rows = [
            {"Zeile": "7", "Beschreibung": "Kapitalerträge", "Betrag_num": kapitalertraege},
            {"Zeile": "8", "Beschreibung": "Gewinne aus Aktienveräußerungen", "Betrag_num": positive_entries},
            {"Zeile": "12", "Beschreibung": "Nicht ausgeglichene Verluste aus der Veräußerung von Aktien", "Betrag_num": negative_entries},
            {"Zeile": "18", "Beschreibung": "Inländische Kapitalerträge", "Betrag_num": kapitalertraege_de},
            {"Zeile": "19", "Beschreibung": "Ausländische Kapitalerträge", "Betrag_num": kapitalertraege_ausl},

            {"Zeile": "20", "Beschreibung": "In den Zeilen 18 und 19 enthaltene Gewinne aus Aktienveräußerungen i. S. d. § 20 Abs. 2 Satz 1 Nr. 1 EStG", "Betrag_num": positive_entries_ausl},
            {"Zeile": "23", "Beschreibung": "In den Zeilen 18 und 19 enthaltene Verluste aus der Veräußerung von Aktien i. S. d. § 20 Abs. 2 Satz 1 Nr. 1 EStG", "Betrag_num": negative_entries_ausl},

            {"Zeile": "37", "Beschreibung": "Kapitalertragsteuer", "Betrag_num": kapitalertragsteuer_divi},
            {"Zeile": "38", "Beschreibung": "Solidaritätszuschlag", "Betrag_num": soli_divi},
            {"Zeile": "41", "Beschreibung": "Anrechenbare ausländische Steuern", "Betrag_num": anrechenb_ausl_steuer}
        ]
    
    anlage_kap = pd.DataFrame(tax_rows)
    anlage_kap["Betrag"] = anlage_kap["Betrag_num"].apply(lambda x: f"{x:.2f} EUR")

    save_to_excel(anlage_kap, output_path)



if __name__ == "__main__":
    pdf_path = "/Users/alexanderheinz/Library/Mobile Documents/com~apple~CloudDocs/Documents/steuer/2023/degiro_Jahresübersicht 2023.pdf"
    current_dir = os.path.dirname(os.path.abspath(__file__))
    excel_output = os.path.join(current_dir, 'output.xlsx')

    main(pdf_path, excel_output)
