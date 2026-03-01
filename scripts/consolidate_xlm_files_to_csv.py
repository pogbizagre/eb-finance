import os
import logging
import pandas as pd

from src.xml_files.utils import list_xml_files
from src.xml_files.parse_xml_files import ParseXmlFile


XMLS_SRC_PATH = 'C:/dev/read_xml/xml_files'

# Create and configure logger
logging.basicConfig(filename="logs/consolidate_xml_files.log",
                    format='%(asctime)s %(message)s',
                    filemode='w')

# Creating an object
logger = logging.getLogger('consolidate_xml_files')

# Setting the threshold of logger to DEBUG
logger.setLevel(logging.INFO)

xml_files_full_path = list_xml_files(XMLS_SRC_PATH)
logger.info(f" All XML files : {xml_files_full_path}")

output_file = os.path.join(XMLS_SRC_PATH, "consolidated_sms.csv")
all_data = []
processed_bodies = set()  # To keep track of unique 'body' values

for file_path in xml_files_full_path:
    xml_parser = ParseXmlFile(path=file_path)
    transactions = xml_parser.read_xml_file(file_path)
    for transaction in transactions:
        if transaction not in processed_bodies:
            all_data.append({'body': transaction})
            processed_bodies.add(transaction)

if all_data:
    df = pd.DataFrame(all_data)
    df.to_csv(output_file, index=False, encoding='utf-8')
    logger.info(f"Fichier CSV consolidé créé avec succès : {output_file}")
else:
    logger.info("Aucune donnée à consolider.")