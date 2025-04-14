import os
import re
import pandas as pd
import xml.etree.ElementTree as ET

from datetime import datetime

def extract_transaction_info(text):
    """Extrait les informations d'un message de transaction Orange Money."""

    type_transaction = "inconnu"  # Valeur par défaut
    montant = None
    numero_expediteur = None
    nom_expediteur = None
    solde = None
    id_transaction = None

    # Recherche du type de transaction (plusieurs variantes)
    # type_match = re.search(r"(recu|transfere|Transfert d argent)", text, re.IGNORECASE)
    # if type_match:
    #     type_transaction = type_match.group(1).lower()  # Convertir en minuscule
        
    # Type de transaction (vérification de la présence des mots "reçu" ou "transféré")
    if re.search(r"recu", text, re.IGNORECASE):
        type_transaction = "DEPOT"
    elif re.search(r"transfere", text, re.IGNORECASE):
        type_transaction = "RETRAIT"
    else:
        type_transaction = "INCONNU"

    # Recherche du montant (plusieurs formats)
    montant_match = re.search(r"(\d+(?:,\d+)?(?:.\d+)?) FCFA", text) # Ajout de (?:.\d+)? pour les centimes
    if montant_match:
        montant = float(montant_match.group(1).replace(",", ""))

    # Numéro de l'expéditeur (amélioration pour gérer le format "numéro (nom)")
    numero_match = re.search(r"(?:de|du|de l'expéditeur )([+]?\d+)", text)  # Inclure le + pour les numéros internationaux
    if numero_match:
        numero_expediteur = numero_match.group(1)
    else:  # Si le format habituel n'est pas trouvé, chercher le numéro avant le nom entre parenthèses
        numero_match = re.search(r"([+]?\d+)\s*\(", text)  # Numéro avant parenthèse
        if numero_match:
            numero_expediteur = numero_match.group(1)
    
    # Nom de l'expéditeur (amélioration pour gérer le format "numéro (nom)")
    nom_match = re.search(r"(?:,|\()([A-Za-z\s]+)(?:\)|,|\.)", text)
    if nom_match:
        nom_expediteur = nom_match.group(1).strip()
    else:  # Si le format habituel n'est pas trouvé, chercher le nom après le numéro
        nom_match = re.search(r"\(\s*([A-Za-z\s]+)\s*\)", text)  # Nom entre parenthèses
        if nom_match:
            nom_expediteur = nom_match.group(1).strip()

    # Recherche du solde (plusieurs formats)
    solde_match = re.search(r"(?:solde est de|Nouveau solde OM :|solde de votre compte est de)\s*(\d+(?:.\d+)?)\s*FCFA", text, re.IGNORECASE)
    if solde_match:
        solde = float(solde_match.group(1).replace(",", ""))

    # Recherche de l'identifiant de la transaction (plusieurs formats)
    id_match = re.search(r"(?:ID Trans:|ID :|Trans ID:) (\w+\.\d+\.\d+|\w+)", text)  # Gérer les ID plus courts
    if id_match:
        id_transaction = id_match.group(1)
        
    date_transaction = None
    if id_transaction:
        date_match = re.search(r"(\w{2})(\d{2})(\d{2})?\.", id_transaction)  # JJMMAA
        if date_match:
            try:
                jour = int(date_match.group(3))
                mois = int(date_match.group(2))
                annee = 2000 + int(date_match.group(1))  # Ajouter 2000 pour obtenir l'année complète
                date_transaction = datetime(annee, mois, jour).strftime("%Y-%m-%d")  # Format YYYY-MM-DD
            except ValueError:
                pass  # Gérer les erreurs de conversion de date

    return {
        "text" : text,
        "type_transaction": type_transaction,
        "montant": montant,
        "numero_expediteur": numero_expediteur,
        "nom_expediteur": nom_expediteur,
        "solde": solde,
        "id_transaction": id_transaction,
        "date_transaction": date_transaction,
    }

    
xlm_files_folder_path = 'xlm_files/'
xlm_files = os.listdir(xlm_files_folder_path)
all_transactions_df = []
for i in range(len(xlm_files)) :
    # Parse the XML file
    xlm_file_path = os.path.join(xlm_files_folder_path, xlm_files[i])
    print(f"Reading file {xlm_file_path}")

    tree = ET.parse(xlm_file_path)
    root = tree.getroot()

    # Access specific elements
    for element in root.findall('sms'):
        body_text = element.attrib.get('body')  # Get the "body" attribute
        print("Texte :", body_text)
        infos = extract_transaction_info(body_text)
        df = pd.DataFrame([infos])
        all_transactions_df.append(df)
        print(infos)
        print("-" * 20)
        
# Concaténation de tous les DataFrames en un seul
all_transactions_df = pd.concat(all_transactions_df, ignore_index=True)
print(f"Shape before dropping duplicates {all_transactions_df.shape}")

unique_transactions_df = all_transactions_df.drop_duplicates()
print(f"Shape after dropping duplicates {unique_transactions_df.shape}")

current_month = datetime.now().strftime("%b").lower()
# Sauvegarde du DataFrame dans un fichier CSV

unique_transactions_df.to_csv(f"all_transactions_{current_month}.csv", index=False, encoding="utf-8") 