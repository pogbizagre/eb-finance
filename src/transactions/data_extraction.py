import re

from datetime import datetime
from src.data.utils import Regexes, ColumnsNames

class DataExtraction:
    
    def __init__(self, text):
        self.text = text
    
    def get_transactn_id(self):
        # Recherche de l'identifiant de la transaction (plusieurs formats)
        id_match = re.search(Regexes.ID_RE.value, self.text)
        if id_match:
            self.transactn_id = id_match.group(1)
            
    def get_transactn_type(self) :
        # Type de transaction (vérification de la présence des mots "reçu" ou "transféré")
        if re.search(Regexes.TRANSACTN_RECIEVED_RE.value, self.text, re.IGNORECASE):
            self.transactn_type = "DEPOT"
        elif re.search(Regexes.TRANSACTN_TRANSFER_RE.value, self.text, re.IGNORECASE):
            self.transactn_type = "RETRAIT"
        else:
            self.transactn_type = "INCONNU"
        
    def  get_transactn_amount(self) :
        # Recherche du montant (plusieurs formats)
        transactn_amt_match = re.search(Regexes.AMOUNT_RE.value, self.text)
        if transactn_amt_match:
            self.transactn_amt = float(transactn_amt_match.group(1).replace(",", ""))
            
    def get_transactn_balance_amt(self):
        # Recherche du solde (plusieurs formats)
        balance_match = re.search(Regexes.BALANCE_RE.value, self.text, re.IGNORECASE)
        if balance_match:
            self.balance_amt = float(balance_match.group(1).replace(",", ""))
    
    def get_transactn_date(self):
        # Recherche de la date de transaction
        if self.transactn_id:
            date_match = re.search(Regexes.DATE_RE.value, self.transactn_id)  # JJMMAA
            if date_match:
                jour = int(date_match.group(3))
                mois = int(date_match.group(2))
                annee = 2000 + int(date_match.group(1))  # Ajouter 2000 pour obtenir l'année complète
                self.transactn_dt = datetime(annee, mois, jour).strftime("%Y-%m-%d")  # Format YYYY-MM-DD
                
    def get_transactn_sender_number(self):
        # Numéro de l'expéditeur (amélioration pour gérer le format "numéro (nom)")
        number_match = re.search(Regexes.NUMBER_RE.value, self.text)
        if number_match:
            self.sender_number = number_match.group(1)
        else:
            # Si le format habituel n'est pas trouvé, chercher le numéro avant le nom entre parenthèses
            number_match = re.search(Regexes.NUMBER_OPT_RE.value, self.text)
            if number_match:
                self.sender_number = number_match.group(1)
                
    def get_transactn_sender_name(self):
        # Nom de l'expéditeur (amélioration pour gérer le format "numéro (nom)")
        name_match = re.search(Regexes.NAME_RE.value, self.text)
        if name_match:
            self.sender_name = name_match.group(1).strip()
        else:
            # Si le format habituel n'est pas trouvé, chercher le nom après le numéro
            name_match = re.search(Regexes.NAME_OPT_RE.value, self.text)
            if name_match:
                self.sender_name = name_match.group(1).strip()
                
    def get_transactn_data(self) :
        
        self.get_transactn_id()
        self.get_transactn_type()
        self.get_transactn_amount()
        self.get_transactn_date()
        self.get_transactn_balance_amt()
        self.get_transactn_sender_number()
        self.get_transactn_sender_name()
        
        self.transactn_data =  {
            ColumnsNames.TRANSACTN_ID.value: self.transactn_id,
            ColumnsNames.TRANSACTN_TYPE.value: self.transactn_type,
            ColumnsNames.TRANSACTN_AMT.value: self.transactn_amt,
            ColumnsNames.TRANSACTN_DATE.value: self.transactn_dt,
            ColumnsNames.BALANCE_AFTER_TRANSACTN.value: self.balance_amt,
            ColumnsNames.TRANSACTN_SENDER_NUMBER.value: self.sender_number,
            ColumnsNames.TRANSACTN_SENDER_NAME.value: self.sender_name,
            ColumnsNames.BODY_TEXT.value: self.text,
        }
        
        return self.transactn_data
