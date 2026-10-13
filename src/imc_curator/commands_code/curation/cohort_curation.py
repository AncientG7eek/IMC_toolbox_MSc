class CurationProject:
    def __init__(project, destination, project_name):

        if "http" in destination:
            #download from link to a specified dir and unzip
            pass
        
        # create filesystem for new curation project in projects/{project_name}/

class Cohort:
    def __init__(cohort, path):
        cohort.completed_steps = {"raw"}
        cohort.repository_path = path

        # discover_images(cohort)
        # load_clinical(cohort)
        # find_metadata(cohort)
        # find_patients(cohort)

        #let the user validate or correct the findings

        # harmonize_markers(cohort)
        # validate(cohort)

    def discover_images(cohort):
        """
        searches for tiff/npy etc. in repository, 
        extracts and creates symlinks to them in
        images dir. Reports num imgs found and the
        origin path to them.
        """
        cohort.completed_steps.add("images")

    def load_clinical(cohort):
        """
        searches for csv with some heauristic determination 
        in repository, saves it to clinical folder and reports
        the origin path. Uses another heuristic to match images
        to patients and suggests it to the user
        """
        cohort.completed_steps.add("clinical")

    def find_patients(cohort):
        """
        looks for a patient column in clinical dataframe
        saves to patient file, reports
        """
        cohort.completed_steps.add("patients")

    def find_metadata(cohort):
        """
        looks both for specific file and metadata in ometiff etc.
        which contain the channel-> marker mapping. Saves to 
        metadata file and reports the origin path
        """
        cohort.completed_steps.add("metadata")

    def harmonize_markers(cohort):
        """
        parses the metadata file, tries to match them to current
        marker base, saves the json with standard marker names to
        the marker file. Reports the matching process to the user. 
        """
        cohort.completed_steps.add("markers")

    def validate(cohort):
        """
        runs some asserts to make sure all the necessary 
        objects were created and they have consistent
        formats. Reports the results to a yaml file."""
        cohort.completed_steps.add("validation")