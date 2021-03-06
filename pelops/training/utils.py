from pelops.datasets.chip import ChipDataset
from pelops.utils import SetType
import json
import os
import os.path


def tuple_to_string(tup):
    """Convert a tuple (or other iterable, we are not picky) to a string.

    Args:
        tup (tuple): An iterable full of items on which str() works.

    Returns:
        str: A string of all elements of the tuple, joined with underscores.
    """
    return "_".join(str(i) for i in tup)


def attributes_to_classes(chip_dataset, chip_key_maker):
    """Extract a set of attributes from a set of Chips and uses them to make
    unique classses.

    The chip_key_maker is a function (or other callable) with the following
    signature:

        chip_key_maker(chip) -> string

    It returns a string derived from the chip. All chips that output the same
    string will be considered as part of the same class for training. An
    example key_maker might do the following:

        chip_key_maker(chip) -> "honda_civic"

    The strings will be sorted first before an index is assigned, so that the
    first string alphabetically will have index 0. This increases the
    reproducibility of the dictionary as only changes to the number of classes,
    not to the chips, will change the dictionary.

    Args:
        chip_dataset: A ChipDataset, or other iterable of Chips
        chip_key_maker: A function that takes a chip and returns a string
            derived from the chip.

    Returns:
        dict: a dictionary mapping the output of chip_key_maker(chip) to a
            class number.
    """
    # First we get all the keys
    keys = set()
    for chip in chip_dataset:
        # Get the class from the specified attributes
        key = chip_key_maker(chip)
        keys.add(key)

    class_to_index = {}
    for index, key in enumerate(sorted(keys)):
        class_to_index[key] = index

    return class_to_index


def key_make_model(chip):
    """ Given a chip, return make and model string.

    Make and model are extracted from chip.misc using the keys "make" and
    "model". If they are missing it returns None for that value. If misc
    missing or not a dictionary, (None, None) is returned.

    Args:
        chip: A chip named tuple

    Returns:
        string: "make_model" from the chip. The string "None" may be returned
            for one of the positions (or both) if it is missing in the chip.
    """
    output = [None, None]
    # Ensure we have a misc dictionary
    if hasattr(chip, "misc"):
        misc = chip.misc
        if hasattr(misc, "get"):
            output[0] = misc.get("make", None)
            output[1] = misc.get("model", None)

    return tuple_to_string(output)


def key_color(chip):
    """ Given a chip, returns the color as a string.

    Color is extracted from chip.misc using the key "color". If it is missing
    or misc is not a dictionary, str(None) is returned

    Args:
        chip: A chip named tuple

    Returns:
        str: color from the chip. str(None) if not defined, or misc is
            missing.
    """
    output = [None]
    # Ensure we have a misc dictionary
    if hasattr(chip, "misc"):
        misc = chip.misc
        # Get the make and model
        if hasattr(misc, "get"):
            output[0] = misc.get("color", None)

    return tuple_to_string(output)


def key_make_model_color(chip):
    """ Given a chip, returns the make, model, and color as a string.

    Color is extracted from chip.misc using the keys "make, "model", and
    "color". If misc missing or not a dictionary, "None_None_None" is returned.

    Args:
        chip: A chip named tuple

    Returns:
        str: "make_model_color" from the chip. str(None) may be returned for
            one of the positions (or any number of them) if it is missing in
            the chip.
    """
    make_model = key_make_model(chip)
    color = key_color(chip)
    return "_".join((make_model, color))


class KerasDirectory(object):
    def __init__(self, chip_dataset, chip_key_maker):
        """ Takes a ChipDataset and hard links the files to custom defined
        class directories.

        Args:
            chip_dataset: A ChipDataset, or other iterable of Chips
            chip_key_maker: A callable that takes a chip and returns a string
                representing the attributes in that chip that you care about.
                For example, you might write a function to return the make and
                model, or color.
        """
        # Set up internal variables
        self.__chip_dataset = chip_dataset
        self.__chip_key_maker = chip_key_maker

        # Class setup functions
        self.__set_root_dir()

        # Set up the class to index mapping
        self.__class_to_index = attributes_to_classes(
            self.__chip_dataset,
            self.__chip_key_maker,
        )
        print(self.__class_to_index)

    def __set_root_dir(self):
        """ Set the root directory for the classes based on the SetType.

        If self.__chip_dataset.set_type exists, it will be used to
        set the root directory name, otherwise it will default to
        "all".

        The final directory will be:

        output_directory / root / class_number / image
        """
        ROOTMAP = {
            SetType.ALL.value: "all",
            SetType.QUERY.value: "query",
            SetType.TEST.value: "test",
            SetType.TRAIN.value: "train",
        }

        # We write a train, test, query, or all directory as the root depending
        # on the ChipDataset.
        self.root = "all"
        try:
            set_type = self.__chip_dataset.set_type
        except AttributeError:
            return

        try:
            key = set_type.value
        except AttributeError:
            return

        try:
            self.root = ROOTMAP[set_type.value]
        except KeyError:
            return

    def write_links(self, output_directory, root=None, write_map=True):
        """ Writes links to a directory.

        The final directory will be:

        output_directory / root / class_number / image

        Where root is set by self.__set_root_dir() and is based on
        the SetType, but you can reset it by passing in root.

        Args:
            output_directory (str): The location to write the files to, it must
                already exist.
            root (str, Defaults to None): A base directory to create in the
                output_directory, under which all further directories will be
                written. If not specified, the class will choose between
                "test", "train", "query", and "all" depending on the `SetType`
                of the `chip_dataset`. If you would like no directory, use a
                blank string "".
            write_map (bool, defaults to True): If true, writes a JSON file of
                the self.__class_to_index map.
        """
        # Override root with self.root if not set
        if root is None:
            root = self.root

        # Write a Class to number map JSON
        if write_map:
            map_dir = os.path.join(output_directory, root)
            os.makedirs(map_dir, exist_ok=True)
            self.write_map(map_dir)

        # Link chips
        for chip in self.__chip_dataset:
            src = chip.filepath
            filename = os.path.basename(src)
            chip_class = self.__chip_key_maker(chip)
            chip_index = self.__class_to_index[chip_class]
            dest_dir = os.path.join(output_directory, root, str(chip_index))

            os.makedirs(dest_dir, exist_ok=True)
            dst = os.path.join(dest_dir, filename)
            os.link(src=src, dst=dst)

    def write_map(self, output_directory, filename="class_to_index_map.json"):
        """Write the class_to_index map to a JSON file.

        Args:
            output_directory (str): The location to write the map to.
            filename (str, defaults to class_to_index_map.json): the filename
                to save the JSON file to.
        """
        full_path = os.path.join(output_directory, filename)
        with open(full_path, "w") as open_file:
            json.dump(self.__class_to_index, open_file, indent=2)
