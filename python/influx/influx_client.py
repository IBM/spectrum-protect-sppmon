"""Module with influx client. Contains all functionality arround sending and accessing influx database.

Classes:
    InfluxClient
"""
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError, InfluxDBServerError
from influxdb.resultset import ResultSet

from influx.database_tables import Database, RetentionPolicy, Table
from influx.definitions import Definitions
from influx.influx_queries import (ContinuousQuery, InsertQuery, Keyword,
                                   SelectionQuery)
from utils.execption_utils import ExceptionUtils
from utils.spp_utils import SppUtils

LOGGER = logging.getLogger("sppmon")


class InfluxClient:
    """Class uses for accessing and working with the influx client.

    Attributes:
        database - database with predefined tables
        use_ssl - whether the client should use ssl.

    Methods:
        connect - connects the client to remote sever
        disconnect - disconnects the client from remote server and flush buffer
        check_create_rp - Checks if any retention policy needs to be altered or added
        check_create_cq - Checks if any continuous query needs to be altered or added
        insert_dicts_to_buffer - Method to insert data into influxb
        flush_insert_buffer - flushes buffer, send querys to influxdb
        send_selection_query - sends a single `SelectionQuery` to influxdb
        copy_database - copies whole database into a new one

        @depricated
        update_row - updates values and tags of already saved data

    """

    @property
    def use_ssl(self):
        """Whether the client should use ssl"""
        return self.__use_ssl

    @property
    def database(self):
        """Database with predef tables. Access by [tablename] to gain instance"""
        return self.__database

    __insert_buffer: Dict[Table, List[InsertQuery]] = {}
    """used to send all insert-querys at once. Multiple Insert-Querys per table"""

    __query_max_batch_size = 10000
    """Maximum amount of querys sent at once to the influxdb. Recommended is 5000-10000."""

    def __init__(self, config_file: Dict[str, Any]):
        """Initalize the influx client from a config dict. Call `connect` before using the client.

        Arguments:
            auth_influx {dictonary} -- Dictionary with required parameters.

        Raises:
            ValueError: Raises a ValueError if any important parameters are missing within the file
        """
        if(not config_file):
            raise ValueError("A config file is required to setup the InfluxDB client.")

        auth_influx = SppUtils.get_cfg_params(param_dict=config_file, param_name="influxDB")
        if(not isinstance(auth_influx, dict)):
            raise ValueError("The InfluxDB config is corrupted within the file: Needs to be a dictionary.")

        try:
            self.__user: str = auth_influx["username"]
            self.__password: str = auth_influx["password"]
            self.__use_ssl: bool = auth_influx["ssl"]
            if(self.__use_ssl):
                self.__verify_ssl: bool = auth_influx["verify_ssl"]
            else:
                self.__verify_ssl = False
            self.__port: int = auth_influx["srv_port"]
            self.__address: str = auth_influx["srv_address"]
            self.__database: Database = Database(auth_influx["dbName"])

            # Create table definitions in code
            Definitions.add_table_definitions(self.database)

            self.__metrics_table: Table = self.database['influx_metrics']
        except KeyError as key_error:
            ExceptionUtils.exception_info(error=key_error)
            raise ValueError(
                "Missing Influx-Config arg", str(key_error))

        # declare for later
        self.__client: InfluxDBClient

    def connect(self) -> None:
        """Connect client to remote server. Call this before using any other methods.

        Raises:
            ValueError: Login failed
        """
        try:
            self.__client: InfluxDBClient = InfluxDBClient( # type: ignore
                host=self.__address,
                port=self.__port,
                username=self.__user,
                password=self.__password,
                ssl=self.__use_ssl,
                verify_ssl=self.__verify_ssl,
                timeout=20
            )

            # ping to make sure connection works
            version: str = self.__client.ping()
            LOGGER.debug(f"Connected to influxdb, version: {version}")

            # create db, nothing happens if it already exists
            self.__client.create_database(self.database.name)

            # check for exisiting retention policies and continuous queries in the influxdb
            self.check_create_rp(self.database.name)
            self.check_create_cq()

        except (ValueError, InfluxDBClientError, InfluxDBServerError, requests.exceptions.ConnectionError) as error: # type: ignore
            ExceptionUtils.exception_info(error=error) # type: ignore
            raise ValueError("Login into influxdb failed")

    def disconnect(self) -> None:
        """Disconnects client from remote server and finally flushes buffer."""
        LOGGER.debug("disconnecting Influx database")

        # Double send to make sure all metrics are send
        try:
            self.flush_insert_buffer()
            self.flush_insert_buffer()
        except ValueError as error:
            ExceptionUtils.exception_info(
                error=error,
                extra_message="Failed to flush buffer on logout, possible data loss")
        self.__client.close()


    def check_create_rp(self, database_name: str) -> None:
        """Checks if any retention policy needs to be altered or added

        Raises:
            ValueError: Multiple RP declared as default
            ValueError: Check failed due Database error
        """
        try:
            results: List[Dict[str, Any]] = self.__client.get_list_retention_policies(database_name)

            rp_dict: Dict[str, Dict[str, Any]] = {}
            for result in results:
                rp_dict[result['name']] = result

            add_rp_list: List[RetentionPolicy] = []
            alter_rp_list: List[RetentionPolicy] = []
            default_used = False

            for retention_policy in self.database.retention_policies:
                # make sure only one RP is default
                if(retention_policy.default):
                    if(default_used):
                        raise ValueError("multiple Retention Policies are declared as default")
                    default_used = True

                result_rp = rp_dict.get(retention_policy.name, None)
                if(result_rp is None):
                    add_rp_list.append(retention_policy)
                elif(result_rp != retention_policy.to_dict()):
                    alter_rp_list.append(retention_policy)
                # else: all good
            LOGGER.debug(f"missing {len(add_rp_list)} RP's. Adding {add_rp_list}")
            for retention_policy in add_rp_list:
                self.__client.create_retention_policy( # type: ignore
                    name=retention_policy.name,
                    duration=retention_policy.duration,
                    replication=retention_policy.replication,
                    database=database_name,
                    default=retention_policy.default,
                    shard_duration=retention_policy.shard_duration
                )
            LOGGER.debug(f"altering {len(add_rp_list)} RP's. altering {add_rp_list}")
            for retention_policy in alter_rp_list:
                self.__client.alter_retention_policy( # type: ignore
                    name=retention_policy.name,
                    duration=retention_policy.duration,
                    replication=retention_policy.replication,
                    database=database_name,
                    default=retention_policy.default,
                    shard_duration=retention_policy.shard_duration
                )

        except (ValueError, InfluxDBClientError, InfluxDBServerError, requests.exceptions.ConnectionError) as error: # type: ignore
            ExceptionUtils.exception_info(error=error) # type: ignore
            raise ValueError("Retention Policies check failed")

    def check_create_cq(self) -> None:
        """Checks if any continuous query needs to be altered or added

        Raises:
            ValueError: Check failed due Database error
        """
        try:
            results: List[Dict[str, List[Dict[str, Any]]]] = self.__client.get_list_continuous_queries()

            cq_result_list: Optional[List[Dict[str, Any]]] = None
            for result in results:
                # check if this is the associated database
                cq_result_list = result.get(self.database.name, None)
                if(cq_result_list is not None):
                    break
            if(cq_result_list is None):
                cq_result_list = []

            cq_dict: Dict[str, ContinuousQuery] = {}
            for cq_result in cq_result_list:
                cq_dict[cq_result['name']] = cq_result['query']

            add_cq_list: List[ContinuousQuery] = []
            alter_cq_list: List[ContinuousQuery] = []

            for continuous_query in self.database.continuous_queries:

                result_cq = cq_dict.get(continuous_query.name, None)
                if(result_cq is None):
                    add_cq_list.append(continuous_query)
                elif(result_cq != continuous_query.to_query()):
                    alter_cq_list.append(continuous_query)
                # else: all good

            LOGGER.debug(f"altering {len(add_cq_list)} CQ's. deleting {add_cq_list}")
            # alter not possible -> drop and readd
            for continuous_query in alter_cq_list:
                self.__client.drop_continuous_query(  # type: ignore
                    name=continuous_query.name,
                    database=continuous_query.database.name
                )
            # extend to reinsert
            add_cq_list.extend(alter_cq_list)
            LOGGER.debug(f"adding {len(add_cq_list)} CQ's. adding {add_cq_list}")
            for continuous_query in add_cq_list:
                self.__client.create_continuous_query( # type: ignore
                    name=continuous_query.name,
                    select=continuous_query.select,
                    database=continuous_query.database.name,
                    resample_opts=continuous_query.resample_opts)


        except (ValueError, InfluxDBClientError, InfluxDBServerError, requests.exceptions.ConnectionError) as error: # type: ignore
            ExceptionUtils.exception_info(error=error) # type: ignore
            raise ValueError("Continuous Query check failed")

    def copy_database(self, new_database_name: str = None) -> None:
        if(not new_database_name):
            raise ValueError("copy_database requires a new database name to copy to.")

        # Programm information
        LOGGER.info(f"Copy Database: transfering the data from database {self.database.name} into {new_database_name}.")
        LOGGER.info("> Info: This also includes all data from `autogen` retention policy, sorted into the correct retention policies.")

        # create db, nothing happens if it already exists
        LOGGER.info("> Creating the new database if it didn't already exist")
        self.__client.create_database(new_database_name)

        # check for exisiting retention policies and continuous queries in the influxdb
        LOGGER.info(">> Checking and creating retention policies for the new database. Ignoring continuous queries.")
        self.check_create_rp(new_database_name)
        # self.check_create_cq() # Note: Not possible due full qualified statements. this would also not truly conserve the data

        LOGGER.info("> Computing queries to be send to the server.")
        queries: List[str] = []
        # copies all tables into their respective duplicate, data over RP-time will be dropped.
        for table in self.database.tables.values():
            autogen_query_str = f"SELECT * INTO {new_database_name}.{table.retention_policy.name}.{table.name} FROM {table.database.name}.autogen.{table.name} WHERE time > now() - {table.retention_policy.duration} GROUP BY *"
            queries.append(autogen_query_str)

            rp_query_str = f"SELECT * INTO {new_database_name}.{table.retention_policy.name}.{table.name} FROM {table} WHERE time > now() - {table.retention_policy.duration} GROUP BY *"
            queries.append(rp_query_str)

        # Compute data with a timestamp over the initial RP-duration into other RP's.
        for con_query in self.database.continuous_queries:
            cq_query_str: str = con_query.to_query()

            # replacing the rp inside of the toString representation
            # this is easier than individual matching/code replacement
            # Not every database name should be replaced
            match = re.search(r"BEGIN(.*(INTO\s+(.+)\..+\..+)\s+(FROM\s+\w+\.(\w+)\.\w+)(?:\s+WHERE\s+(.+))?\s+GROUP BY.*)END", cq_query_str)
            if(not match):
                raise ValueError(f">> error when matching continous query {cq_query_str}. Aborting.")

            full_match = match.group(1)
            into_clause = match.group(2)
            old_database_str = match.group(3)
            from_clause = match.group(4)
            from_rp = match.group(5)
            where_clause = match.group(6)

            # Add timelimit in where clause to prevent massive truncation due the rentention-policy time limit
            new_full_match = full_match
            if(not con_query.select_query or con_query.select_query.into_table is None):
                    ExceptionUtils.error_message(f">> Into table of continous query is none. Adjust query manually! {full_match}")
            elif(con_query.select_query.into_table.retention_policy.duration != '0s'):
                    # Caution: if truncation of a query is above 10.000 it won't be saved!
                    clause = f"time > now() - {con_query.select_query.into_table.retention_policy.duration}"
                    if(where_clause):
                        new_full_match = new_full_match.replace(where_clause, where_clause + " AND " + clause)
                    else:
                        new_full_match = new_full_match.replace(from_clause, from_clause + " WHERE " + clause)

            # replace old dbname with new one
            new_into_clause = into_clause.replace(old_database_str, new_database_name)
            new_full_match = new_full_match.replace(into_clause, new_into_clause)

            # case 1: keep retention policy
            queries.append(new_full_match)

            # case 2: autogen as from RP
            new_from_clause = from_clause.replace(from_rp, "autogen")
            auto_gen_match = new_full_match.replace(from_clause, new_from_clause)
            queries.append(auto_gen_match)

        LOGGER.info("> Finished Computing, starting to send.")

        # how many lines were transfered
        line_count: int = 0
        # how often was a query partially written, not line count!
        dropped_count: int = 0
        # how often was data dropped above the 10.000 limit?
        critical_drop: int = 0

        # print statistics
        # send time since last print
        send_time_collection: float = 0
        # line count since last print
        line_collection: int = 0

        # disable timeout
        old_timeout = self.__client._timeout
        self.__client = InfluxDBClient( # type: ignore
            host=self.__address,
            port=self.__port,
            username=self.__user,
            password=self.__password,
            ssl=self.__use_ssl,
            verify_ssl=self.__verify_ssl,
            timeout=7200
        )
        # ping to make sure connection works
        version: str = self.__client.ping()
        LOGGER.info(f">> Connected to influxdb with new timeout of {self.__client._timeout}, version: {version}")
        LOGGER.info(">> Starting transfer of data")
        i = 0

        for query in queries:
            try:
                start_time = time.perf_counter()
                # seems like you may only send one SELECT INTO at once via python
                result = self.__client.query( # type: ignore
                    query=query, epoch='s', database=self.database.name)
                end_time = time.perf_counter()

                # count lines written, max 1
                for result in result.get_points():
                    i += 1
                    line_count += result["written"]

                    # print statistics
                    send_time_collection += end_time-start_time
                    line_collection += result["written"]

                    # Print only all 10 queries or if the collected send time is too high
                    if(i % 10 == 0 or send_time_collection >= 2):
                        LOGGER.info(f'query {i}/{len(queries)}: {line_collection} new lines in {send_time_collection}s.')
                        line_collection = 0
                        send_time_collection = 0

            except InfluxDBClientError as error:
                # only raise if the error is unexpected
                if(re.search(f"partial write: points beyond retention policy dropped=10000", error.content)):
                    critical_drop += 1
                    raise ValueError(">> transfer of data failed, retry manually with a shorter WHERE-clause", query)
                if(re.search(f"partial write: points beyond retention policy dropped=", error.content)):
                    dropped_count += 1
                else:
                    ExceptionUtils.exception_info(error=error, extra_message=f">> transfer of data failed for query {query}")
                    critical_drop += 1

            except (InfluxDBServerError, requests.exceptions.ConnectionError) as error:
                ExceptionUtils.exception_info(error=error, extra_message=f">> transfer of data failed for query {query}")
                critical_drop += 1

        # reset timeout
        self.__client = InfluxDBClient( # type: ignore
            host=self.__address,
            port=self.__port,
            username=self.__user,
            password=self.__password,
            ssl=self.__use_ssl,
            verify_ssl=self.__verify_ssl,
            timeout=old_timeout
        )
        # ping to make sure connection works
        version: str = self.__client.ping()
        LOGGER.info(f">> Changed timeout of influxDB to old timeout of {self.__client._timeout}, version: {version}")

        LOGGER.info(f"> Total transfered {line_count} lines of results.")
        if(dropped_count):
            LOGGER.info(f"> WARNING: Could not count lines of {dropped_count} queries due an expected error. No need for manual action.")
        if(critical_drop):
            msg: str = (f"ERROR: Could not transfer data of {critical_drop} tables, check messages above to retry manually!\n"+
                        "Please send the query manually with a adjusted 'from table': '$database.autogen.tablename'\n "+
                        "Adjust other values as required. Drop due Retention Policy is 'OK' until 10.000.\n"+
                        "If the drop count reaches 10.000 you need to cut the query into smaller bits.")
            ExceptionUtils.error_message(msg)
        elif(line_count == 0):
            ExceptionUtils.error_message("ERROR: No data was transferred, make sure your database name is correct and the db is not empty.")
        else:
            LOGGER.info("Database copied sucessfully")



    def insert_dicts_to_buffer(self, table_name: str, list_with_dicts: List[Dict[str, Any]]) -> None:
        """Insert a list of dicts with data into influxdb. Splits according to table definition.

        It is highly recommened to define a table before in database_table.py. If not present, splits by type analysis.
        Important: Querys are only buffered, not sent. Call flush_insert_buffer to flush.

        Arguments:
            table_name {str} -- Name of the table to be inserted
            list_with_dicts {List[Dict[str, Any]]} -- List with dicts whith collum name as key.

        Raises:
            ValueError: No list with dictonarys are given or of wrong type.
            ValueError: No table name is given
        """
        LOGGER.debug(f"Enter insert_dicts for table: {table_name}")
        if(list_with_dicts is None): # empty list is allowed
            raise ValueError("missing list with dictonarys in insert")
        if(not table_name):
            raise ValueError("table name needs to be set in insert")

        # Only insert of something is there to insert
        if(not list_with_dicts):
            LOGGER.debug("nothing to insert for table %s due empty list", table_name)
            return

        # get table instance
        table = self.database[table_name]

        # Generate querys for each dict
        query_buffer = []
        for mydict in list_with_dicts:
            try:
                # split dict according to default tables
                (tags, values, timestamp) = table.split_by_table_def(mydict=mydict)

                if(isinstance(timestamp, str)):
                    timestamp = int(timestamp)
                # LOGGER.debug("%d %s %s %d",appendCount,tags,values,timestamp)

                # create query and append to query_buffer
                query_buffer.append(InsertQuery(table, values, tags, timestamp))
            except ValueError as err:
                ExceptionUtils.exception_info(error=err, extra_message="skipping single dict to insert")
                continue

        # extend existing inserts by new one and add to insert_buffer
        table_buffer = self.__insert_buffer.get(table, list())
        table_buffer.extend(query_buffer)
        self.__insert_buffer[table] = table_buffer
        LOGGER.debug("Appended %d items to the insert buffer", len(query_buffer))

        # safeguard to avoid memoryError
        if(len(self.__insert_buffer[table]) > 5 * self.__query_max_batch_size):
            self.flush_insert_buffer()

        LOGGER.debug(f"Exit insert_dicts for table: {table_name}")

    def flush_insert_buffer(self) -> None:
        """Flushes the insert buffer, send querys to influxdb server.

        Sends in batches defined by `__batch_size` to reduce http overhead.
        Only send-statistics remain in buffer, flush again to send those too.

        Raises:
            ValueError: Critical: The query Buffer is None.
        """

        if(self.__insert_buffer is None):
            raise ValueError("query buffer is somehow None, this should never happen!")
        # Only send if there is something to send
        if(not self.__insert_buffer):
            return

        # Done before to be able to clear buffer before sending
        # therefore stats can be re-inserted
        insert_list: List[Tuple[Table, List[str]]] = []
        for(table, queries) in self.__insert_buffer.items():

            insert_list.append((table, list(map(lambda query: query.to_query(), queries))))

        # clear all querys which are now transformed
        self.__insert_buffer.clear()

        for(table, queries_str) in insert_list:

            # stop time for send progess
            start_time = time.perf_counter()
            try:
                # send batch_size querys at once
                self.__client.write_points(
                    points=queries_str, database=self.database.name,
                    retention_policy=table.retention_policy.name,
                    batch_size=self.__query_max_batch_size,
                    time_precision='s', protocol='line')
            except (InfluxDBServerError, InfluxDBClientError, ConnectionError) as error: # type: ignore
                ExceptionUtils.exception_info(error=error, extra_message="Error when sending Insert Buffer") # type: ignore
            end_time = time.perf_counter()

            # add metrics for the next sending process.
            # compute duration, metrics computed per batch
            self.__insert_metrics_to_buffer(
                Keyword.INSERT, {table:len(queries_str)}, end_time-start_time, len(queries_str))

    def __insert_metrics_to_buffer(self, keyword: Keyword, tables_count: Dict[Table, int],
                                   duration_s: float, batch_size: int = 1) -> None:
        """Generates statistics per send Batch, total duration is split by item per table.

        Arguments:
            keyword {Keyword} -- Kind of query.
            tables_count {dict} -- Tables send in this batch, key is table, value is count of items.
            duration_s {float} -- Time needed to send the batch in seconds.

        Keyword Arguments:
            batch_size {int} -- Ammount of queries sent in one batch sent at once. (default: {1})

        Raises:
            ValueError: Any arg does not match the defined parameters or value is unsupported
        """
        # Arg checks
        if(list(filter(lambda arg: arg is None, [keyword, tables_count, duration_s, batch_size]))):
            raise ValueError("any metric arg is None. This is not supported")
        if(not isinstance(keyword, Keyword)):
            raise ValueError("need the keyword to be a instance of keyword.")
        if(not tables_count or not isinstance(tables_count, dict)):
            raise ValueError("need at least one entry of a table in tables_count.")
        if(duration_s <= 0):
            raise ValueError("only positive values are supported for duration. Must be not 0")
        if(batch_size < 1):
            raise ValueError("only positive values are supported for batch_size. Must be not 0")

        # get shared record time to be saved on
        querys = []

        # save metrics for each involved table individually
        for (table, item_count) in tables_count.items():
            querys.append(
                InsertQuery(
                    table=self.__metrics_table,
                    fields={
                        # Calculating relative duration for this part of whole query
                        'duration_ms':  duration_s*1000*(max(item_count, 1)/batch_size),
                        'item_count':   item_count,
                    },
                    tags={
                        'keyword':      keyword,
                        'tableName':    table.name,
                    },
                    time_stamp=SppUtils.get_actual_time_sec()
                ))
        self.__insert_buffer[self.__metrics_table] = self.__insert_buffer.get(self.__metrics_table, []) + querys

    def update_row(self, table_name: str, tag_dic: Dict[str, str] = None,
                   field_dic: Dict[str, Union[str, int, float, bool]] = None, where_str: str = None):
        """DEPRICATED: Updates a row of the given table by given tag and field dict.

        Applies on multiple rows if `where` clause is fullfilled.
        Updates row by row, causing a high spike in call times: 3 Influx-Querys per call.
        Simple overwrite if no tag is changed, otherwise deletes old row first.
        Possible to add new values to old records.
        No replacement method available yet, check jobLogs (jobs update) how to query, then delete / update all at once.

        Arguments:
            table_name {str} -- name of table to be updated

        Keyword Arguments:
            tag_dic {Dict[str, str]} -- new tag values (default: {None})
            field_dic {Dict[str, Union[str, int, float, bool]]} -- new field values (default: {None})
            where_str {str} -- clause which needs to be fullfilled, any matched rows are updated (default: {None})

        Raises:
            ValueError: No table name is given.
            ValueError: Neither tag nor field dic given.
        """
        # None or empty checks
        if(not table_name):
            raise ValueError("Need table_name to update row")
        if(not tag_dic and not field_dic):
            raise ValueError(f"Need either new field or tag to update row in table {table_name}")

        keyword = Keyword.SELECT
        table = self.database[table_name]
        query = SelectionQuery(
            keyword=keyword, fields=['*'], tables=[table], where_str=where_str)
        result = self.send_selection_query(query) # type: ignore
        result_list: List[Dict[str, Union[int, float, bool, str]]] = list(result.get_points()) # type: ignore

        # no results found
        if(not result_list):
            return

        # split between remove and insert
        # if tag are replaced it is needed to remove the old row first
        if(tag_dic):
            # WHERE clause reused
            keyword = Keyword.DELETE
            table = self.database[table_name]
            query = SelectionQuery(
                keyword=keyword, tables=[table], where_str=where_str)
            self.send_selection_query(query)

        insert_list = []
        for row in result_list:
            if(tag_dic):
                for (key, value) in tag_dic.items():
                    row[key] = value
            if(field_dic):
                for (key, value) in field_dic.items():
                    row[key] = value
            insert_list.append(row)

        # default insert method
        self.insert_dicts_to_buffer(table_name, insert_list)


    def send_selection_query(self, query: SelectionQuery) -> ResultSet: # type: ignore
        """Sends a single `SELECT` or `DELETE` query to influx server.

        Arguments:
            query {Selection_Query} -- Query which should be executed

        Raises:
            ValueError: no SelectionQuery is given.

        Returns:
            ResultSet -- Result of the Query, Empty if `DELETE`
        """
        if(not query or not isinstance(query, SelectionQuery)):
            raise ValueError("a selection query must be given")

        # check if any buffered table is selected, flushes buffer
        for table in query.tables:
            if(table in self.__insert_buffer):
                self.flush_insert_buffer()
                break

        # Convert querys to strings
        query_str = query.to_query()

        start_time = time.perf_counter()
        # Send querys
        try:
            result = self.__client.query( # type: ignore
                query=query_str, epoch='s', database=self.database.name)

        except (InfluxDBServerError, InfluxDBClientError) as err: # type: ignore
            ExceptionUtils.exception_info(error=err, extra_message="error when sending select statement") # type: ignore
            # result to maintain structure
            # raise errors = false since we did catch a error
            result: ResultSet = ResultSet({}, raise_errors=False) # type: ignore

        end_time = time.perf_counter()

        # if nothing is returned add count = 0 and table
        # also possible by `list(result.get_points())`, but that is lot of compute action
        if(result):
            length = len(result.raw['series'][0]['values']) # type: ignore
        else:
            length = 0

        tables_count: Dict[Table, int] = {}
        for table in query.tables:
            tables_count[table] = int(length/len(query.tables))

        self.__insert_metrics_to_buffer(query.keyword, tables_count, end_time-start_time)

        return result # type: ignore
