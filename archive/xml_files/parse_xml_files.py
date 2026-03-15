import xml.etree.ElementTree as ET

class ParseXmlFile :
    def __init__(self, path):
        self.path = path
    
    def read_xml_file(self, tags: str = 'sms'):
        
        tree = ET.parse(self.path)
        root = tree.getroot()
        
        all_transactn = []
        # Access specific tags elements
        for element in root.findall(tags):
            # Get the "body" attribute
            all_transactn.append(element.attrib.get('body'))
            
        return all_transactn