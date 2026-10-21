from pathlib import Path
from imc_curator.config import load_search_config
import pandas as pd

def markers_csv_parser(markers_file_path: Path) -> str:
    marker_table = pd.read_csv(markers_file_path)
    marker_table["KEEP/REJECT [0/1]"] = ""
    # make a text to the panel report where there is
    # obligatory field to enter the col_name of marker column
    # facultative field to enter the colname of channel number
    # facultative field to enter the colname of metal isotope
    # facultative field to enter a regex expression which will parse the values in marker column to clean marker names
    # marker table with added column (like above)
    # the filled form will be the input to next command which will parse the form so the form needs to be parsable
    markers_form_text = f"""
        Form regarding: {markers_file_path}

        This is the form you need to fill to parse the file with marker panel 
        which was provided in the IMC repository you are curating now...

        
    """

    return markers_form_text

def clinical_csv_parser(clinical_file_path: Path, example_image_paths: list(Path)) -> str:
    clinical_table = pd.read_csv(clinical_file_path)[:6]
    clinical_table.loc[len(clinical_table)] = pd.Series([1] * len(clinical_table.columns))
    # make a text to the clinical form where thewre is
    # obligatory field to entrer a column name which holds some ID (of patient/ image/ ROI) by which clinical_row-image connection can be made 
    # obligatory field to entrer a regex expression which will parse the values in the ID column

    clinical_form_text = f"""
        Form regarding: {clinical_file_path}

        This is the form you need to fill to parse the file with clinical features [{clinical_file_path}]
        which was provided in the IMC repository you are curating now...

        Here are some exemplary image file names (together with the project relative path):
        {'\n'.join(example_image_paths)}

        Here is 5 first rows of the clinical features table with an appended row of 1s. 
        Please substitute 1 with 0 in the column which IS NOT A CLINICAL FEATURE OR IS 
        A CLINICAL FEATURE YOU DON'T WANT TO KEEP

        {clinical_table}

        Now please enter the name of the column which holds the IDs which can connect the table row to the corresponding image:
        [answer]>

        Now please enter the regex expressions which will allow to parse an image file name and the ID in such way that we can match
        them by assigning equality between these 2 regex results.
        [answer: image name regex]>""
        [answer: ID value regex]>""
    """

    return clinical_form_text

def create_form(text: str, output_path: Path) -> Path:
    # write the text to a file and return path to the file
    return output_path


def csv_parser(project_dir: Path) -> str:
    search_config = load_search_config()
    images_path = project_dir / search_config["categories"]["images"]["destination"]
    markers_path = project_dir / search_config["categories"]["markers"]["destination"]
    clinical_path = project_dir / search_config["categories"]["clinical"]["destination"]

    image_path_examples = []
    for path in images_path.rglob("*"):
        while len(image_path_examples) <= 5:
            image_path_examples.append(path)

    markers_forms = {}
    for path in markers_path.rglob("*"):
        markers_form_text = markers_csv_parser(markers_file_path=path)
        markers_forms[path] = markers_form_text

    clinical_forms = {}
    for path in clinical_path.rglob("*"):
        clinical_form_text = clinical_csv_parser(clinical_file_path=path, example_image_paths=image_path_examples)
        clinical_forms[path] = clinical_form_text

    markers_forms_paths = []
    for path, text in markers_forms.items():
        output_path = project_dir / "curation_manifest" / "examine" / f"markers_form_{path.name}"
        markers_forms_paths.append(output_path)

    clinical_forms_paths = []
    for path, text in clinical_forms.items():
        output_path = project_dir / "curation_manifest" / "examine" / f"clinical_form_{path.name}"
        clinical_forms_paths.append(output_path)

    return f"Wrote: \n- markers forms paths:\n{'\n  - '.join(markers_forms_paths)}\n\n - clinical forms paths:\n{'\n  - '.join(clinical_forms_paths)}"