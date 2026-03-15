from enum import Enum

class Regexes(Enum):
    
    TRANSACTN_RECIEVED_RE = r"recu"
    TRANSACTN_TRANSFER_RE = r"transfere"
    AMOUNT_RE = r"(\d+(?:,\d+)?(?:.\d+)?) FCFA"
    NUMBER_RE = r"(?:de|du|de l'expéditeur )([+]?\d+)"
    NUMBER_OPT_RE = r"([+]?\d+)\s*\("
    NAME_RE = r"(?:,|\()([A-Za-z\s]+)(?:\)|,|\.)"
    NAME_OPT_RE = r"\(\s*([A-Za-z\s]+)\s*\)"
    BALANCE_RE = r"(?:solde est de|Nouveau solde OM :|solde de votre compte est de)\s*(\d+(?:.\d+)?)\s*FCFA"
    ID_RE = r"(?:ID Trans:|ID :|Trans ID:) (\w+\.\d+\.\d+|\w+)"
    DATE_RE = r"(\w{2})(\d{2})(\d{2})?\."
    

class ColumnsNames(Enum):
    BODY_TEXT = "BODY_TEXT"
    TRANSACTN_TYPE = "TRANSACTN_TYPE"
    TRANSACTN_AMT = "TRANSACTN_AMT"
    TRANSACTN_SENDER_NUMBER = "TRANSACTN_SENDER_NUMBER"
    TRANSACTN_SENDER_NAME = "TRANSACTN_SENDER_NAME"
    TRANSACTN_ID = "TRANSACTN_ID"
    TRANSACTN_DATE = "TRANSACTN_DATE"
    BALANCE_AFTER_TRANSACTN = "BALANCE_AFTER_TRANSACTN"