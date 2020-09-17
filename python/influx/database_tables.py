"""Provides all database and table structures used for the influx database.

Classes:
    Datatype
    Database
    Table
    RetentionPolicy
"""
from __future__ import annotations
from enum import Enum, unique
import re
import json
from typing import Any, Dict, List, Set, Tuple, Union

import influx.influx_queries as Queries
from utils.execption_utils import ExceptionUtils
from utils.influx_utils import InfluxUtils
from utils.spp_utils import SppUtils

@unique
class Datatype(Enum):
    """
    This enum differentiates between the different Influx-Types.

    By declaring the type SPPMon will automatically insert the data in the right format.
    The order of the types within the enum is important: bool is a int, but a int is not a bool.
    Important: only use `TIME` for epoch timestamps, *NOT* for durations or counts.
    `TIME` is automatically converted into second format.
    Note: The return type is just a helper and not of a big use.

    Methods:
        get_auto_datatype - get Datatype enum by value typ analysis
    """

    NONE = type(None)
    """Undeclared, only use as a placeholder."""

    STRING = str
    """Special symbols and \" will be escaped."""

    BOOL = bool
    """Any boolean, be aware it is a subtype of int.
    TODO Untested, saves as Boolean within Influx.
    """

    INT = int
    """Appends a 'i' at end of number to declare. Fails if the data is mixed with any other type."""

    FLOAT = float
    """Unchanged value. Default Influx numeric data type. Mixing with ints works."""

    TIMESTAMP = type(int)
    """Automatic transform a timestamp into seconds. Important: Only use for Epoch timestamps, not duration or counter.
    Caution: Type is just a placeholder, do not set to int - causing problems!
    """

    @staticmethod
    def get_auto_datatype(value: Any) -> Datatype:
        """get Datatype enum by value typ analysis. Usage should be avoided.

        Only use if no datatype is declared. It skips time-type and fails if ints are mixed with floats.
        If no type is detected emits a warning and returns `NONE`.

        Arguments:
            value {Union[str, float, int, bool, None]} -- Value to be analyzed

        Returns:
            Datatype -- type of value or `NONE`.
        """
        for enum in Datatype:
            if(enum is Datatype.TIMESTAMP):
                continue
            if(isinstance(value, enum.value)):
                return enum

        ExceptionUtils.error_message(f"No auto type found for {value}")
        return Datatype.NONE

class RetentionPolicy:
    """Represents a influxdb retention policy.

    By this policy it is declared afer which ammount of time a dataset is deleted from the DB.

    Attributes
        name - name of RP
        database - associated database
        duration - time until the data is purged
        replication - How often the date is replicated
        shard_duration - Size of memory-groups
        default - whether this is the default RP
    Methods
        to_dict - creates a dict out of the values
    """

    @property
    def name(self) -> str:
        """name of the Retention Policy"""
        return self.__name

    @property
    def database(self) -> Database:
        """associated database"""
        return self.__database

    @property
    def duration(self) -> str:
        """time until the data is purged"""
        return self.__duration

    @property
    def replication(self) -> int:
        """How often the date is replicated. We only have 1 db instance so replication is always 1"""
        return self.__replication

    @property
    def shard_duration(self) -> str:
        """Size of memory-groups. Default time is 0s, then the db decides what to take"""
        return self.__shard_duration

    @property
    def default(self) -> bool:
        """ whether this is the default RP"""
        return self.__default

    def __init__(self, name: str, database: Database, duration: str,
                 replication: int = 1, shard_duration: str = "0s",
                 default: bool = False) -> None:
        if(not name):
            raise ValueError("need retention policy name for creation")
        if(not database):
            raise ValueError("need retention policy database for creation")
        if(not duration):
            raise ValueError("need retention policy duration for creation")
        if(not replication):
            raise ValueError("need retention policy replication factor for creation")
        if(not shard_duration):
            raise ValueError("need retention policy shard duration for creation")
        if(default is None):
            raise ValueError("need retention policy default setting for creation")

        self.__name = name
        self.__database = database
        self.__replication = replication
        self.__shard_duration = shard_duration
        self.__default = default
        try:
            # str due usage of method
            self.__duration: str = InfluxUtils.transform_time_literal(duration, single_vals=False)
        except ValueError as error:
            ExceptionUtils.exception_info(error)
            raise ValueError(f"duration for retention policy {name} is not in the correct time format")
        try:
            # str due usage of method
            self.__shard_duration: str = InfluxUtils.transform_time_literal(shard_duration, single_vals=False)
        except ValueError as error:
            ExceptionUtils.exception_info(error)
            raise ValueError(f"shard duration for retention policy {name} is not in the correct time format")

    def to_dict(self) -> Dict[str, Union[str, int, bool]]:
        """Used to create a dict out of the values, able to compare to influxdb-created dict"""
        return {
            'name':                 self.name,
            'duration':             self.duration,
            'shardGroupDuration':   self.__shard_duration,
            'replicaN':             self.__replication,
            'default':              self.default
        }

    def __str__(self) -> str:
        return f"{self.database.name}.{self.name}"

    def __repr__(self) -> str:
        return f"Retention Policy: {self.name}"

    def __eq__(self, o: object) -> bool:
        if(isinstance(o, RetentionPolicy)):
            return o.to_dict() == self.to_dict()
        return False

    def __hash__(self) -> int:
        return hash(json.dumps(self.to_dict(), sort_keys=True))

class Table:
    """Represents a measurement in influx. Contains pre-defined tag and field definitions.

    Attributes
        name - name of table
        fields - dict of field name with datatype
        tags - tags as list of str
        time_key - key name of the timestamp field

    Methods
        split_by_table_def - Split the given dict into a pre-defined set of tags, fields and a timestamp.
    """
    @property
    def fields(self) -> Dict[str, Datatype]:
        """fields of the table, name is key, value is datatype"""
        return self.__fields

    @property
    def tags(self) -> List[str]:
        """tags of the table, datatype always string"""
        return self.__tags

    @property
    def time_key(self) -> str:
        """name of the timestamp key"""
        return self.__time_key

    @property
    def name(self) -> str:
        """name of the table"""
        return self.__name

    @property
    def retention_policy(self) -> RetentionPolicy:
        """retention policy associated with this table"""
        return self.__retention_policy

    @property
    def database(self) -> Database:
        """table is declared within this database"""
        return self.__database

    __bad_measurement_characters: List[str] = [' ', ',']
    """those chars need to be escaped within a measurement/table name"""

    def __init__(self, database: Database, name: str, fields: Dict[str, Datatype] = None,
                 tags: List[str] = None, time_key: str = 'time', retention_policy: RetentionPolicy = None) -> None:

        if(not database):
            raise ValueError("need database to create table")
        if(not name):
            raise ValueError("need str name to create table")
        if(not time_key):
            raise ValueError("time key cannot be None")
        if(not fields):
            fields = {}
        if(not tags):
            tags = []

        self.__database: Database = database
        self.__fields: Dict[str, Datatype] = fields
        self.__tags: List[str] = tags
        self.__time_key: str = time_key
        self.__retention_policy = retention_policy

        # escape not allowed characters in Measurement
        for bad_character in self.__bad_measurement_characters:
            if(re.search(bad_character, name)):
                name = name.replace(bad_character, '\\%c'% bad_character)
        self.__name: str = name

    def __str__(self) -> str:
        return f"{self.database.name}.{self.retention_policy.name}.{self.name}"

    def __repr__(self) -> str:
        return f"Table: {self.name}"

    def split_by_table_def(self, mydict: Dict[str, Any]) -> Tuple[
            Dict[str, Any], Dict[str, Any], Union[str, int, None]]:
        """Split the given dict into a pre-defined set of tags, fields and a timestamp.

        None-Values and empty strings are ignored.
        If there are no fields declared, it will split by a default pattern.
        Undeclared collums will be added with a "MISSING" postfix to the key.
        This function uses the tag/field and timestamp definiton declared within this table.

        Arguments:
            self {Table} -- Table with predefined set of tags and fields
            mydict {Dict[str, Any]} -- dict with colums as keys. None-Values are ignored

        Raises:
            ValueError: If no dict is given or not of type dict.

        Returns:
            (Dict[str, Any], Dict[str, Any], int) -- Tuple of: tags, fields, timestamp
        """

        if(not mydict):
            raise ValueError("need at least one value in dict to split")

        # if table is not defined use default split
        if(not self.fields):
            return InfluxUtils.default_split(mydict=mydict)

        # fill dicts
        # table.fields is a dict, we only need the keys
        fields: Dict[str, Any] = dict.fromkeys(self.fields.keys(), None)
        tags: Dict[str, Any] = dict.fromkeys(self.tags, None)

        # what field should be recorded as time
        time_stamp_field = self.time_key
        # helper variable to only overwrite if it is not the time_stamp_field
        time_overwrite_allowed = True
        # actualy timestamp saved
        time_stamp: Union[str, int, None] = None



        for (key, value) in mydict.items():

            # Ignore empty entrys
            if(value is None or (isinstance(value, str) and not value)):
                continue

            # Check timestamp value if it matches any of predefined time names
            if(key in time_stamp_field or key in InfluxUtils.time_key_names):

                # sppmonCTS has lowest priority, only set if otherwise None
                if(time_stamp is None and key == SppUtils.capture_time_key):
                    time_stamp = value

                # time_stamp_field is highest priority. Do not overwrite it.
                elif(key is time_stamp_field):
                    time_overwrite_allowed: bool = False
                    time_stamp = value

                # if time_stamp_field is not used yet, overwrite sppmonCaptureTime or others
                elif(time_overwrite_allowed):
                    time_stamp = value

                # if no overwrite allowed, continue and drop field
                else:
                    continue

            # Otherwise check for Keys or Fields
            if(key in fields):
                fields[key] = value
            elif(key in tags):
                tags[key] = value
            elif(key in InfluxUtils.time_key_names or key in time_stamp_field):
                continue
            else:
                ExceptionUtils.error_message(f"Not all columns for table {self.name} are declared: {key}")
                # before key+"MISSING" : Removed to avoid death-circle on repeated queries.
                fields[key] = value
        return (tags, fields, time_stamp)

class Database:
    """
    Represents a instance of influx database. Define all table definitions within the init method.

    Attributes
        name - name of the database
        tables - tables with predefined tags & fields
        retention_policies - Set of all provided Retention Policies
        continuous_queries - Set of all provided Continuous Queries


    Methods
        __getitem__ - [] access on the tables via name. Creates empty table if missing.
    """

    @property
    def tables(self) -> Dict[str, Table]:
        """Dict with table definitions to look up"""
        return self.__tables

    @property
    def retention_policies(self) -> Set[RetentionPolicy]:
        """Set of all provided Retention Policies"""
        return self.__retention_policies

    @property
    def continuous_queries(self) -> Set[Queries.ContinuousQuery]:
        """Set of all provided Continuous Queries"""
        return self.__continuous_queries

    @property
    def name(self) -> str:
        """name of the database, also used as reference"""
        return self.__name

    def __getitem__(self, table_name: str) -> Table:
        """Aquire a instance of a predefined table, returns a empty table if it was not defined. []-Access.

        Arguments:
            table_name {str} -- name of the table you want to aquire

        Returns:
            Table -- Instance of a predefined table, otherwise new empty table
        """
        return self.tables.get(table_name, Table(self, table_name))

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f'Database: {self.name}'

    def __init__(self, name: str):
        self.__name: str = name
        self.__tables: Dict[str, Table] = {}
        self.__retention_policies: Set[RetentionPolicy] = set()
        self.__continuous_queries: Set[Queries.ContinuousQuery] = set()
