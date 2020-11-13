"""This Module provides helper methods used across all sppmon modules.
You may implement new static/class helper methods in here.

Classes:
    SppUtils
"""
import logging
import json
import time
import re
import os

from pathlib import Path

from numbers import Number
from typing import Any, Optional, Tuple, Dict, Union, List

from utils.execption_utils import ExceptionUtils

LOGGER = logging.getLogger("sppmon")

class SppUtils:
    """Wrapper for general purpose themed helper methods. You may implement new methods in here.

    Attributes:
        verbose - to be set in sppmon.
        capture_time_key - name of the unique capture time stamp.

    Methods:
        read_file - Reads parameters from the JSON file and returns a JSON dict.
        get_cfg_params - Wrapper method to check if the arguments of the config file are correct.
        get_actual_time_sec - returns the actual time as timestamp in seconds.
        get_capture_timestamp_sec - Returns Tuple of the capturetimestamp name and value.
        epoch_time_to_seconds - Converts timestamp from any epoch-format into epoch-seconds.
        get_nested_kv - Aquire a nested key-value pair from a dict with possible sub-dicts.
        parse_unit - Parses a str or number into the lowest unit.

    """

    # class variable
    verbose: bool = False
    """whether to verbose print, set in sppmon.py"""

    capture_time_key: str = "sppmonCaptureTimestampS"
    """name of the single timestamp capture to allow same naming within the db"""

    @staticmethod
    def filename_of_config(conf_file: str, fileending: str) -> str:
        """returns a filepath to the logdir out of the config file + a new fileending

        Args:
            conf_file (str): name of the configfile incl. path
            fileending (str): the new fileending

        Returns:
            str: full path to the file
        """
        if(conf_file):
            cfg_file = conf_file

            # get everything behind the last slash
            config_name = os.path.basename(cfg_file)
            # get name without fileending
            config_name = config_name.split('.')[-2]

            pid_file_name = config_name + fileending
        else:
            pid_file_name = "no_config_file" + fileending

        home_path = Path.home()
        pid_file_dir_path = os.path.join(home_path, "sppmonLogs")
        # create if not existent
        Path(pid_file_dir_path).mkdir(parents=True, exist_ok=True)

        return os.path.join(pid_file_dir_path, pid_file_name)

    @classmethod
    def read_conf_file(cls, config_file_path: str) -> Dict[str, Any]:
        """Reads parameters from the JSON file and returns a JSON dict.

        Arguments:
            config_file_path {str} -- path to the .cong file

        Raises:
            ValueError: no config file specified.
            ValueError: file not consistent.
            ValueError: file not found.

        Returns:
            Dict[str, Any] -- Config file as JSON dict
        """
        # read parameters from JSON file and returns JSON dictionary if file exists and
        # structure is consistent
        if(config_file_path is None):
            raise ValueError("ERROR:   missing parameter, no config file specified, ... aborting program")
        try:
            with open(config_file_path) as config_file:
                try:
                    settings = json.load(config_file)
                except json.decoder.JSONDecodeError as error: # type: ignore
                    ExceptionUtils.exception_info(error=error) # type: ignore
                    raise ValueError("parameter file '{config_file}' not consistent"
                                     .format(config_file=config_file_path)) from error

        except FileNotFoundError as error:
            ExceptionUtils.exception_info(error)
            raise ValueError("parameter file '{config_file}' not found"
                             .format(config_file=config_file_path)) from error

        return settings

    @classmethod
    def get_cfg_params(cls, param_dict: Dict[str, Union[List[Dict[str, Any]], Dict[str, Any]]],
            param_name: str) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Wrapper method to check if the arguments of the config file are correct.

        Arguments:
            param_dict {Dict[str, Union[List[Dict[str, Any]], Dict[str, Any]]]} -- auth file as json dict.
            param_name {str} -- name of the elem you want to query.

        Raises:
            ValueError: no param dict given or not of type dict
            ValueError: no param name given or not string
            ValueError: no config found for param name or completly empty
            ValueError: config found is not a dict or list.
            ValueError: parameters within the config are none.

        Returns:
            Union[List[Dict[str, Any]], Dict[str, Any]] -- The selected config without none values.
        """
        if(not param_dict or not isinstance(param_dict, dict)):
            raise ValueError("param_dict is empty or None")
        if(not param_name or not isinstance(param_name, str)):
            raise ValueError("need param name to get element")

        cfg = param_dict.get(param_name, None)
        if(not cfg):
            raise ValueError("{param_name} config does not exist or is empty".format(param_name=param_name))
        if(not isinstance(cfg, (dict, list))):
            raise ValueError(f"config under {param_name} is not a dict or a list: {cfg}")
        if(None in cfg):
            raise ValueError('Parameters within {param_name} are None: {dict}'.format(param_name=param_name, dict=cfg))

        return cfg

    @staticmethod
    def get_actual_time_sec() -> int:
        """returns the actual time as timestamp in seconds."""
        return int(round(time.time()))

    @classmethod
    def get_capture_timestamp_sec(cls) -> Tuple[str, int]:
        """Returns Tuple of the capturetimestamp name and value"""
        return cls.capture_time_key, cls.get_actual_time_sec()


    @staticmethod
    def to_epoch_secs(time_stamp: Union[str, int, float]) -> int:
        """Converts timestamp from any epoch-format into epoch-seconds precision.

        Arguments:
            time_stamp {Union[str, int, float]} -- timestamp to be converted.

        Raises:
            ValueError: unsupported type

        Returns:
            int -- epoch timestamp in second format
        """
        if(isinstance(time_stamp, str)):
            time_stamp = time_stamp.strip(" ")
            if(re.match(r"\d+", time_stamp)):
                time_stamp = int(time_stamp)
            elif(re.match(r"\d+\.\d+", time_stamp)):
                time_stamp = float(time_stamp)
        if(not isinstance(time_stamp, (int, float))):
            raise ValueError("unsupported timestamp type")

        # convert ms or ns to seconds
        # that is the limit to ms format
        while(time_stamp >= 99999999999):
            time_stamp /= 1000

        return int(time_stamp)


    @staticmethod
    def get_nested_kv(key_name: str, nested_dict: Dict[str, Any]) -> Tuple[str, Optional[Any]]:
        """Aquire a nested key-value pair from a dict with possible sub-dicts.

        Travels along the dynamic path defined in keyName to the result.
        If the path does not exist returns the searched key and None.

        Arguments:
            keyName {str} -- Path to the value wanted
            nested_dict {Dict[str, Any]} -- dictonary with values beeing other dictonarys or the result.

        Raises:
            ValueError: no str key given.
            ValueError: no dict given.

        Returns:
            Tuple[str, Optional[Any]] -- key with the searched result or None if not found
        """
        if(not key_name or not isinstance(key_name, str)):
            raise ValueError("need path to key as string to find elem.")
        if(not nested_dict or not isinstance(nested_dict, dict)):
            raise ValueError("need dictonary to find elem within it")

        # split into multiple sub-levels
        key_list = key_name.split('.')

        sub_dict: Union[Any, Dict[str, Any]] = nested_dict

        # go deeper until result is found
        # at least one key available due arg check above
        for key in key_list:

            # path is available -> go on
            if(key in sub_dict):

                # sub_dict is now either another sub_dict or the result
                sub_dict = sub_dict[key]

            # path is wrong or not existent
            else:
                # return wanted key and None
                return key_list[-1], None

        # key is now lowest level with right value
        return (key_list[-1], sub_dict)


    __display_datatype = 1 # Bytes are displayed as bytes
    __datatypes: Dict[str, int] = {
        'no type':          1,

        # DATA
        # assumed its byte, not bit
        'b':                pow(2, 0) / __display_datatype,

        'k':                pow(2, 10) / __display_datatype,
        'kb':               pow(10, 3) / __display_datatype,
        'kib':              pow(2, 10) / __display_datatype,

        #'m':               pow(2, 20) / __display_datatype, NOTE: Duplicate key, unused anyway
        'mb':               pow(10, 6) / __display_datatype,
        'mib':              pow(2, 20) / __display_datatype,

        'g':                pow(2, 30) / __display_datatype,
        'gb':               pow(10, 9) / __display_datatype,
        'gib':              pow(2, 30) / __display_datatype,

        't':                pow(2, 40) / __display_datatype,
        'tb':               pow(10, 12) / __display_datatype,
        'tib':              pow(2, 40) / __display_datatype,

        # TIME

        'second(s)':        pow(60, 0),
        'second':           pow(60, 0),
        's':                pow(60, 0),

        'min(s)':           pow(60, 1),
        'm':                pow(60, 1),

        'hour(s)':          pow(60, 2),
        'h':                pow(60, 2),

        'd':                pow(60, 2) * 24,

        'w':                pow(60, 2) * 24 * 7
    }

    @classmethod
    def parse_unit(
            cls, data: Union[str, Number], given_unit: str = None,
            delimiter: str = " ") -> Optional[Union[int, Number]]:
        """Parses a str or number into the lowest unit.

        Specify a delimiter if used, default splitting by space.
        Only specify `given unit` if the unit is not within the data itself.
        specify `unit_start_pos` if the unit is within data without delimiter.
        check dict `datatypes` for parseable units.

        Arguments:
            data {Union[str, Number]} -- data w/wo unit to be parsed.

        Keyword Arguments:
            given_unit {str} -- specify if no unit is given. (default: {None})
            delimiter {str} -- delimiter to split val and unit (default: {" "})

        Raises:
            ValueError: no string or number value given
            ValueError: delimiter is None
            ValueError: index error while parsing
            ValueError: no datatype known in `datatypes`
            ValueError: value is not numeric

        Returns:
            Optional[Union[int, Number]] -- Either the data in lowest unit or None if it failed.
        """

        if(not data):
            return None
        if(isinstance(data, Number)):
            return data

        if(not isinstance(data, str)):
            raise ValueError("need string value to parse unit")
        if(data == 'null'):
            return None
        if(delimiter is None):
            raise ValueError("delimteter cannot be None")

        data_parts = list(map(lambda part: part.strip(" "), data.split(delimiter)))

        i: int = 0
        final_value: Union[int, float] = 0

        while(i < len(data_parts)):
            value = data_parts[i]
            i += 1
            unit = 'no type'

            # get correct value and unit
            if(given_unit):
                unit = given_unit
            else:
                unit_match = re.match(r"(-?\d+(?:\.\d+)?)([a-zA-Z]+)", value)
                if(unit_match):
                    value = unit_match.group(1)
                    if(unit_match.group(2)):
                        unit = unit_match.group(2)
                elif(i < len(data_parts)):
                    unit_match = re.match(r"(\D+)", data_parts[i])
                    if(unit_match and unit_match.group(1)):
                        unit = unit_match.group(1)
                        i += 1

            if(unit.lower() not in cls.__datatypes):
                raise ValueError("no known datatype for value with given unit", value, unit, data_parts)

            # convert value
            if(re.match(r"^-?\d+$", value)):
                value = int(value)
            elif(re.match(r"^-?\d+\.\d+$", value)):
                value = float(value)
            else:
                raise ValueError("value is not numeric", value)

            final_value += value * cls.__datatypes[unit.lower()]

        return round(final_value)
