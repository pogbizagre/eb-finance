import os
def list_xml_files(src_path):
    
        xml_files_full_path = []
        xml_files_names = [path for path in os.listdir(src_path) if path.endswith("xml")]
        for file in xml_files_names :
            xml_files_full_path.append(os.path.join(src_path, file))
            
        return xml_files_full_path