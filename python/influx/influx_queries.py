"""Provides all query structues used for the influxdb.

Classes:
    Keyword
    SelectionQuery
    InsertQuery - Use only inside `influx` Package
    ContinuousQuery - Use only inside `influx` Package

"""
from __future__ import annotations
from enum import Enum, unique
import re

from typing import List, Dict, Any, Union, Tuple, Optional

from utils.spp_utils import SppUtils
from utils.influx_utils import InfluxUtils
import influx.database_tables as Structures


@unique
class Keyword(Enum):
    """Possible types of Statements"""
    SELECT = 'SELECT'
    DELETE = 'DELETE'
    INSERT = 'INSERT'

    def __str__(self) -> str:
        return self.value

class InsertQuery:
    """Dataclass used to insert data into influxdb. Makes sure any data is in the right format.

    Use `toQuery` to compute into string. Do not create a instance outside of `influx_client`.

    Attributes:
        keyword - Always `Keyword.INSERT`
        table - Instance of table to be inserted

    Methods:
        to_query - Computes query to string
        format_fields - Formats fields accordingly to the requirements of the influxdb.
        format_tags - Formats tags accordingly to the requirements of the influxdb.
    """
    # those need to be escaped
    __bad_name_characters: List[Tuple[str, str]] = [(r'=', r'\='), (r' ', r'\ '), (r',', r'\,')]
    """Characters which need to be replaced, as tuple list: (old, new). Reference influx wiki."""

    @property
    def keyword(self) -> Keyword:
        """Always `Keyword.INSERT`"""
        return self.__keyword

    @property
    def table(self) -> Structures.Table:
        """Instance of table to be inserted."""
        return self.__table

    def __init__(self, table: Structures.Table, fields: Dict[str, Any], tags: Dict[str, Any] = None,
                 time_stamp: Union[int, str] = None):
        if(not table):
            raise ValueError("need table to create query")
        if(not fields):
            raise ValueError("need at least one value to create query")
        if(tags is None):
            tags = {}
        if(time_stamp is None):
            time_stamp = SppUtils.get_actual_time_sec()

        # Keyword is always Insert since insert Statement
        self.__keyword = Keyword.INSERT
        self.__table = table

        self.__time_stamp = SppUtils.to_epoch_secs(time_stamp)
        fields = self.format_fields(fields)

        # make sure you have some fields if they are not privided
        if(not list(filter(lambda field_tup: field_tup[1] is not None, fields.items()))):
            # need default def to be able to do anything
            if(not table.fields):
                raise ValueError("fields after formatting empty, need at least one value!")
            # only works for strings, any other addition would corrupt the data
            for (key, datatype) in table.fields.items():
                if(datatype is Structures.Datatype.STRING):
                    fields[key] = '\"autofilled\"'
                    break
            # test again, improvement possible here
            if(not list(filter(lambda field_tup: field_tup[1] is not None, fields.items()))):
                raise ValueError("fields after formatting empty, need at least one value!")

        self.__fields: Dict[str, Union[int, float, str, bool]] = fields
        self.__tags: Dict[str, str] = self.format_tags(tags)

    def __str__(self) -> str:
        return self.to_query()

    def __repr__(self) -> str:
        return f"InsertQuery: {self.to_query()}"

    def to_query(self) -> str:
        """Comutes the query into a string, returning it.

        Returns:
            str -- a full functional insert query as string
        """
        if(self.__tags):
            tag_str = ',{}'.format(
                ",".join(map(lambda row: '{key}={value}'.format(key=row[0], value=row[1]),
                             self.__tags.items())))
        else:
            tag_str = ''

        fields_str = ",".join(
            map(lambda row: '{key}={value}'.format(key=row[0], value=row[1]),
                self.__fields.items()))

        if(self.__time_stamp is not None):
            time_stamp_str = str(self.__time_stamp)
        else:
            time_stamp_str = ""

        return f'{self.table.name}{tag_str} {fields_str} {time_stamp_str}'

    def format_fields(self, fields: Dict[str, Any]) -> Dict[str, Union[int, float, str]]:
        """Formats fields accordingly to the requirements of the influxdb.

        Cast and transforms all values to the required datatype, declared in the given table.
        Escapes all characters which are not allowed, applies to both key and value.

        Arguments:
            table {Table} -- Table with given field declarations
            fields {Dict[str, Any]} -- Dict of all fields to be formatted, key is name, value is data

        Returns:
            Dict[str, Union[int, float, str]] -- Dict with field name as key and data as value
        """
        ret_dict: Dict[str, Union[int, float, str]] = {}
        for(key, value) in fields.items():
            if(value is None or (isinstance(value, str) and not value)):
                continue

            # Get Colum Datatype
            datatype = self.table.fields.get(key, None)
            # If nothing is defined select it automatic
            if(datatype is None):
                datatype = Structures.Datatype.get_auto_datatype(value)

            # Escape not allowed chars in Key
            key = InfluxUtils.escape_chars(value=key, replace_list=self.__bad_name_characters)


            # Format Strings
            if(datatype == Structures.Datatype.STRING):
                value = InfluxUtils.escape_chars(value=value, replace_list=[(r'"', r'\"')])
                value = "\"{}\"".format(value)

            # Make time always be saved in seconds, save as int
            if(datatype == Structures.Datatype.TIMESTAMP):
                value = SppUtils.to_epoch_secs(value)
                value = '{}i'.format(value)

            # Make Integer to an IntLiteral
            if(datatype == Structures.Datatype.INT):
                value = '{}i'.format(value)

            ret_dict[key] = value

        return ret_dict

    def format_tags(self, tags: Dict[str, Any]) -> Dict[str, str]:
        """Formats tags accordingly to the requirements of the influxdb.

        Cast all values to strings and escapes all characters which are not allowed.
        Applies to both key and value.

        Arguments:
            tags {Dict[str, Any]} -- Dict of all tags to be formatted, key is name, value is data

        Returns:
            Dict[str, str] -- Dict with tag name as key and data as value
        """
        ret_dict: Dict[str, str] = {}
        for(key, value) in tags.items():
            if(value is None):
                continue
            if(not isinstance(value, str)):
                value = f"{value}"
            # escape not allowed characters
            key = InfluxUtils.escape_chars(value=key, replace_list=self.__bad_name_characters)
            value = InfluxUtils.escape_chars(value=value, replace_list=self.__bad_name_characters)

            ret_dict[key] = value

        return ret_dict


class SelectionQuery:
    """Dataclass used to send SELECT or DELETE statements to influxdb. Formats fields/tags accordingly.

    Use `to_query` to format data into a string. You may create instances outside of influx_client.

    Attributes:
        tables - table instances which get queried
        keyword - type of query

    Methods:
        to_query - computes query into string

    """

    @property
    def tables(self) -> List[Structures.Table]:
        """table instances which get queried"""
        return self.__tables

    @property
    def keyword(self) -> Keyword:
        """Type of Query, either `Keyword.DELETE` or `Keyword.SELECT`"""
        return self.__keyword

    @property
    def into_table(self) -> Optional[Structures.Table]:
        """table instances which get inserted into"""
        return self.__into_table

    def __init__(self, keyword: Keyword, tables: List[Structures.Table],
                 into_table: Optional[Structures.Table] = None,
                 fields: List[str] = None, where_str: str = None,
                 group_list: List[str] = None, order_direction: str = None,
                 limit: int = 0, s_limit: int = 0):
        if(keyword is None or not isinstance(keyword, Keyword)):
            raise ValueError("Supported keyword is needed to create query.")
        if(keyword is Keyword.DELETE and
           (into_table or fields or group_list or
            order_direction or limit or s_limit)):
            raise ValueError("Delete statement does not support additional fields")
        if(not tables):
            raise ValueError("need a table to gather information from")
        if(limit is None):
            limit = 0
        if(s_limit is None):
            s_limit = 0

        if(fields is not None and fields == []):
            fields = ['*']
        self.__fields = fields

        if(group_list is not None and group_list == []):
            group_list = ['*']
        self.__group_list = group_list

        self.__tables = tables
        self.__into_table = into_table
        self.__where_str = where_str
        self.__keyword = keyword
        self.__order_direction = order_direction
        # Workaround since oder by only supports time
        if(order_direction is None):
            self.__order_by = None
        else:
            self.__order_by = 'time'
        self.__limit = limit
        self.__s_limit = s_limit

    def __str__(self) -> str:
        return self.to_query()

    def __repr__(self) -> str:
        return f"SelectionQuery: {self.to_query()}"

    def to_query(self) -> str:
        """Comutes the query into a string, returning it.

        Returns:
            str -- a full functional selection query as string
        """
        # ##### CLAUSE ######
        if(self.__fields is not None):
            if(self.__fields == ['*']):
                fields_str = '*'
            else:
                fields_str = ','.join(
                    map('{}'.format, self.__fields))
        else:
            fields_str = ''

        # ##### INTO #######

        if(self.into_table):
            into_str = f"INTO {self.into_table}" # not name, using full qualified due __str__
        else:
            into_str = ""

        # ##### FROM #######
        # not table.name used to allow retention policy to be included
        # DELETE does not allow RP to be included
        if(self.keyword == Keyword.DELETE):
            tables_str = 'FROM {tables}'.format(
            tables=','.join(
                map(lambda table: f'{table.name}', self.tables)))
        else:
            tables_str = 'FROM {tables}'.format(
                tables=','.join(
                    map(lambda table: f'{table}', self.tables)))

        # ##### WHERE ######
        if(self.__where_str is not None and self.__where_str):
            where_str = 'WHERE {clause}'.format(clause=self.__where_str)
        else:
            where_str = ''

        # ##### GROUP BY ###
        if(self.__group_list is not None):
            group_str = 'GROUP BY {list}'.format(
                list=','.join(
                    map('{}'.format, self.__group_list)))
        else:
            group_str = ''

        # ##### ORDER BY ###
        # ATM always time, direction is never null (checked on init)
        if(self.__order_by is not None):
            order_str = 'ORDER BY \"{order}\" {direction}'.format(
                order=self.__order_by,
                direction=self.__order_direction
            )
        else:
            order_str = ''

        # ##### LIMIT BY ###
        # 0 disables limit, neg not allowed
        if(self.__limit > 0):
            limit_str = 'LIMIT {limit}'.format(limit=self.__limit)
        else:
            limit_str = ''

        # ##### SLIMIT BY ##
        # 0 disables limit, neg not allowed
        if(self.__s_limit > 0):
            s_limit_str = 'SLIMIT {s_limit}'.format(s_limit=self.__s_limit)
        else:
            s_limit_str = ''

        return '{keyword} {clause} {into} {tables} {where} {group} {order} {limit} {s_limit}'.format(
            keyword=self.keyword,
            into=into_str,
            clause=fields_str,
            tables=tables_str,
            where=where_str,
            group=group_str,
            order=order_str,
            limit=limit_str,
            s_limit=s_limit_str
            ).replace(r'\s\s', r'\s')

class ContinuousQuery:
    """Structure for a Continuous Query with a SELECT-INTO-Query inside.

    Use `to_query` to format data into a string. Do not create a instance outside of module `definitons.py`
    __eq__ and __hash__ implemented for SET-use.

    Attributes:
        name - name of the CQ
        database - database affected by CQ
        select - SELECT-Query as str to be send to influxdb
        select_query - SelectionQuery used to generate CQ if not done by string.
        resample_opts - RESAMPLE-Clause as str to be send to influxdb

    Methods:
        to_query - computes query into a string

    """

    @property
    def name(self):
        """name - name of the CQ"""
        return self.__name

    @property
    def database(self):
        """database - database affected by CQ"""
        return self.__database

    @property
    def select(self) -> str:
        """SELECT-Query as str to be send to influxdb"""
        if(self.select_query):
            return self.select_query.to_query()
        return self.__select_str

    @property
    def select_query(self) -> Optional[SelectionQuery]:
        """SelectionQuery used to create query, None if query is given as str."""
        return self.__select_query

    @property
    def resample_opts(self) -> Optional[str]:
        """RESAMPLE-Clause as str to be send to influxdb"""
        return self.__resample_opts

    def __init__(self, name: str, database: Structures.Database,
                 select_query: SelectionQuery = None, str_query: str = None,
                 every_interval: str = None, for_interval: str = None) -> None:

        if(not name):
            raise ValueError("need name to create a continuous query")
        if(not database):
            raise ValueError("need database to create a continuous query")

        if(every_interval and not InfluxUtils.check_time_literal(every_interval)):
            raise ValueError(f"every_interval for CQ {name} is not a time literal")
        if(for_interval and not InfluxUtils.check_time_literal(for_interval)):
            raise ValueError(f"for_interval for CQ {name} is not a time literal")

        if(select_query and not select_query.into_table):
            raise ValueError("need the into clause within the select query")
        if(select_query and str_query):
            raise ValueError("Both select_query and regex_query specified, can only use one")

        self.__name = name
        self.__database = database
        self.__select_query = select_query
        self.__select_str = str_query
        if(not select_query and not str_query):
            raise ValueError("need a either select query or regex str")

        if(every_interval):
            every_str = f"EVERY {every_interval}"
        else:
            every_str = ""

        if(for_interval):
            for_str = f"FOR {for_interval}"
        else:
            for_str = ""

        if(every_str or for_str):
            self.__resample_opts = f"{every_str} {for_str}"
        else:
            self.__resample_opts = None

    def __str__(self) -> str:
        return self.to_query()

    def __repr__(self) -> str:
        return f"Continuous Query: {self.to_query()}"

    def __eq__(self, o: object) -> bool:
        if(isinstance(o, ContinuousQuery)):
            return o.to_query() == self.to_query()
        return False

    def __hash__(self) -> int:
        return hash(self.to_query())

    def to_query(self) -> str:
        """computes query into a string

        Returns:
            str: full query as str
        """
        if(not self.resample_opts):
            resample_str = ""
        else:
            resample_str = f"RESAMPLE {self.resample_opts}"

        cq_str = f"CREATE CONTINUOUS QUERY {self.name} ON {self.database.name} {resample_str} BEGIN {self.select} END"
        cq_str = re.sub(r'  +', r' ', cq_str)
        return cq_str
