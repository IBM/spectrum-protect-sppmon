"""This Module provides all functionality arround executed jobs.
You may implement new job methods in here.

Classes:
    JobMethods
"""
import datetime
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from influx.influx_client import InfluxClient
from influx.influx_queries import Keyword, SelectionQuery
from sppConnection.api_queries import ApiQueries
from utils.execption_utils import ExceptionUtils
from utils.influx_utils import InfluxUtils
from utils.methods_utils import MethodUtils
from utils.spp_utils import SppUtils

LOGGER = logging.getLogger("sppmon")


class JobMethods:
    """Wrapper for all job related functionality. You may implement new methods in here.

    Methods:
        get_all_jobs - incrementally saves all stored jobsessions, even before first execution of sppmon.
        job_logs -> saves all jobLogs for the jobsessions in influx catalog.

    """

    # only here to maintain for later, unused yet
    __job_log_white_list = [
        "CTGGA2340",
        "CTGGA0071",
        "CTGGA2260",
        "CTGGA2315",
        "CTGGA0550",
        "CTGGA2384"
    ]

    # to be moved somewhere else
    # ######### Add new logs to be parsed here #######################################
    # Structure:
    # Dict with messageID of log as name
    # value is a tuple of
    # #1 the tablename
    # #2 a lambda which maps each elem to a name. Must contain at least one argument!
    # #3 list with keys of additional informations to be saved: (#1: key, #2: rename)
    # the values are delived by the param_list of the joblog
    # if the value is something like 10sec or 10gb use `parse_unit` to parse it.
    __supported_ids: Dict[str,
                          Tuple[
                                str,
                                Callable[[List[Any]], Dict[str, Any]],
                                List[Tuple[str, str]]
                                ]] = {
        'CTGGA2384':
            ('vmBackupSummary',
             lambda params: {
                 "name": params[0],
                 "proxy": params[1],
                 "vsnaps": params[2],
                 "type": params[3],
                 "transportType": params[4],
                 "transferredBytes": SppUtils.parse_unit(params[5]),
                 "throughputBytes/s": SppUtils.parse_unit(params[6]),
                 "queueTimeSec": SppUtils.parse_unit(params[7]),
                 "protectedVMDKs": params[8],
                 "TotalVMDKs": params[9],
                 "status": params[10]
             },
             [] # Additional Information from job-message itself
             ),
        'CTGGA0071':
            ('vmBackupSummary',
             lambda params: {
                 'protectedVMDKs': params[0],
                 'TotalVMDKs': int(params[1]) + int(params[0]),
                 'transferredBytes': SppUtils.parse_unit(params[2]),
                 'throughputBytes/s': SppUtils.parse_unit(params[3]),
                 'queueTimeSec': SppUtils.parse_unit(params[4])
             },
             []
             ),
        'CTGGA0072':
            ('vmReplicateSummary',
             lambda params: {
                 'total': params[0],
                 'failed': params[1],
                 'duration': SppUtils.parse_unit(params[2])
             },
             []
             ),
        'CTGGA0398':
            ('vmReplicateStats',
             lambda params: {
                 'replicatedBytes': SppUtils.parse_unit(params[0]),
                 'throughputBytes/sec': SppUtils.parse_unit(params[1]),
                 'duration': SppUtils.parse_unit(params[2], delimiter=':')
             },
             []
             ),
        'CTGGR0003':
            ('office365Stats',
            lambda params: {
                'imported365Users': int(params[0]),
            },
            [ # Additional Information from job-message itself, including rename
                ("jobId", "jobId"),
                ("jobSessionId", "jobSessionId"),
                ("jobName", "jobName"),
                ("jobExecutionTime", "jobExecutionTime") # used to instantly integrate with other stats
            ]
            ),
        'CTGGA2444':
            ('office365Stats',
            lambda params: {
                 'protectedItems': int(params[0]),
                 'selectedItems': int(params[0]),
             },
             [
                ("jobId", "jobId"),
                ("jobSessionId", "jobSessionId"),
                ("jobName", "jobName"),
                ("jobExecutionTime", "jobExecutionTime")  # used to instantly integrate with other stats
             ]
             ),
        'CTGGA2402':
            ('office365TransfBytes',
            lambda params:
            # If not matching, this will return a empty dict which is going to be ignored
                MethodUtils.joblogs_parse_params(
                    r"(\w+)\s*\(Server:\s*([^\s,]+), Transfer Size: (\d+(?:.\d*)?\s*\w*)\)",
                    params[1],
                    lambda match_list:
                        {
                            "itemName": params[0],
                            "itemType": match_list[1],
                            "serverName": match_list[2],
                            "transferredBytes": SppUtils.parse_unit(match_list[3]),
                        }
                ),
                [
                    ("jobId", "jobId"),
                    ("jobSessionId", "jobSessionId"),
                    ("jobName", "jobName")
                ]
                ),
    }
    """LogLog messageID's which can be parsed by sppmon. Check detailed summary above the declaration."""

    def __init__(self, influx_client: Optional[InfluxClient], api_queries: Optional[ApiQueries],
                 job_log_retention_time: str, job_log_type: str, verbose: bool):

        if(not influx_client):
            raise ValueError(
                "Job Methods are not available, missing influx_client")
        if(not api_queries):
            raise ValueError(
                "Job Methods are not available, missing api_queries")

        self.__influx_client = influx_client
        self.__api_queries = api_queries
        self.__verbose = verbose

        self.__job_log_retention_time = job_log_retention_time
        """used to limit the time jobLogs are queried, only interestig for init call"""

        self.__job_log_type = job_log_type

    def get_all_jobs(self) -> None:
        """incrementally saves all stored jobsessions, even before first execution of sppmon"""

        job_list = MethodUtils.query_something(
            name="job list",
            source_func=self.__api_queries.get_job_list
        )

        for job in job_list:
            job_id = job.get("id", None)
            job_name = job.get("name", None)

            # this way to make sure we also catch empty strings
            if(not job_id or not job_name):
                ExceptionUtils.error_message(
                    f"skipping, missing name or id for job {job}")
                continue
            LOGGER.info(
                ">> capturing Job information for Job \"{}\"".format(job_name))

            try:
                self.__job_by_id(job_id=job_id)
            except ValueError as error:
                ExceptionUtils.exception_info(
                    error=error, extra_message=f"error when getting jobs for {job_name}, skipping it")
                continue

    def __job_by_id(self, job_id: str) -> None:
        """Requests and saves all jobsessions for a jobID"""
        if(not job_id):
            raise ValueError("need job_id to request jobs for that ID")

        keyword = Keyword.SELECT
        table = self.__influx_client.database['jobs']
        query = SelectionQuery(
            keyword=keyword,
            fields=['id', 'jobName'],
            tables=[table],
            where_str=f'jobId = \'{job_id}\' AND time > now() - {table.retention_policy.duration}'
            # unnecessary filter?
        )
        LOGGER.debug(query)
        result = self.__influx_client.send_selection_query(  # type: ignore
            query)
        id_list: List[int] = []
        row: Dict[str, Any] = {}  # make sure the var exists
        for row in result.get_points():  # type: ignore
            id_list.append(row['id'])  # type: ignore

        if(not row):
            LOGGER.info(
                f">>> no entries in Influx database found for job with id {job_id}")

        # calculate time to be requested
        (rp_hours, rp_mins, rp_secs) = InfluxUtils.transform_time_literal(
            table.retention_policy.duration, single_vals=True)
        max_request_timestamp = datetime.datetime.now() - datetime.timedelta(
            hours=float(rp_hours),
            minutes=float(rp_mins),
            seconds=float(rp_secs)
        )
        unixtime = int(time.mktime(max_request_timestamp.timetuple()))
        # make it ms instead of s
        unixtime *= 1000

        # retrieve all jobs in this category from REST API, filter to avoid drops due RP
        LOGGER.debug(f">>> requesting job sessions for id {job_id}")
        all_jobs = self.__api_queries.get_jobs_by_id(job_id=job_id)

        # filter all jobs where start time is not bigger then the retention time limit
        latest_jobs = list(filter(lambda job: job['start'] > unixtime, all_jobs))

        missing_jobs = list(filter(lambda job_api: int(job_api['id']) not in id_list, latest_jobs))

        if(len(missing_jobs) > 0):
            LOGGER.info(
                f">>> {len(missing_jobs)} datasets missing in DB for jobId: {job_id}")

            # Removes `statistics` from jobs
            self.__compute_extra_job_stats(missing_jobs, job_id)

            LOGGER.info(f">>> inserting job information of {len(missing_jobs)} jobs into jobs table")
            self.__influx_client.insert_dicts_to_buffer(
                list_with_dicts=missing_jobs,
                table_name="jobs")
        else:
            LOGGER.info(
                f">>> no new jobs to insert into DB for job with ID {job_id}")

        # TODO: artifact from older versions, not replaced yet
        if self.__verbose:
            display_number_of_jobs = 5
            keyword = Keyword.SELECT
            table = self.__influx_client.database['jobs']
            where_str = 'jobId = \'{}\''.format(job_id)
            query = SelectionQuery(
                keyword=keyword,
                fields=['*'],
                tables=[table],
                where_str=where_str,
                order_direction='DESC',
                limit=display_number_of_jobs
            )
            result = self.__influx_client.send_selection_query( # type: ignore
                query)  # type: ignore
            result_list: List[str] = list(
                result.get_points())  # type: ignore

            job_list_to_print: List[str] = []
            for row_str in result_list:
                job_list_to_print.append(row_str)
            print()
            print("displaying last {} jobs for job with ID {} from database (as available)".format(
                display_number_of_jobs, job_id))
            MethodUtils.my_print(data=job_list_to_print)

    def __compute_extra_job_stats(self, list_with_jobs: List[Dict[str, Any]], job_id: str) -> None:
        """Extracts additional `statistic` list from jobs and removes it from the original list.

        Computes an additional table out of the data.

        Args:
            list_with_jobs (List[Dict[str, Any]]): list with all jobs
        """

        LOGGER.info(f">>> computing additional job statistics for jobId: {job_id}")

        insert_list: List[Dict[str, Any]] = []
        # check for none instead of bool-check: Remove empty statistic lists [].
        for job in filter(lambda x: x.get("statistics", None) is not None, list_with_jobs):
            job_statistics_list = job.pop('statistics')

            for job_stats in job_statistics_list:
                try:
                    insert_dict: Dict[str, Any] = {}

                    insert_dict['resourceType'] = job_stats['resourceType']
                    insert_dict['total'] = job_stats.get('total', 0)
                    insert_dict['success'] = job_stats.get('success', 0)
                    insert_dict['failed'] = job_stats.get('failed', 0)

                    skipped = job_stats.get('skipped', None)
                    if(skipped is None):
                       skipped = insert_dict["total"] - insert_dict["success"] - insert_dict["failed"]
                    insert_dict["skipped"] = skipped

                    # time key
                    insert_dict['start'] = job['start']
                    # regular tag values for grouping:
                    insert_dict['id'] = job.get('id', None)
                    insert_dict['jobId'] = job.get('jobId', None)
                    insert_dict['status'] = job.get('status', None)
                    insert_dict['indexStatus'] = job.get('indexStatus', None)
                    insert_dict['jobName'] = job.get('jobName', None)
                    insert_dict['type'] = job.get('type', None)
                    insert_dict['subPolicyType'] = job.get('subPolicyType', None)

                    insert_list.append(insert_dict)
                except KeyError as error:
                    ExceptionUtils.exception_info(error=error, extra_message=
                    f"failed to compute job-individual statistics due key error. report to developer. Job: {job} ; job_stats: {job_stats}")

        if(len(insert_list) > 0):
            self.__influx_client.insert_dicts_to_buffer(
                list_with_dicts=insert_list,
                table_name="jobs_statistics")
        else:
            LOGGER.info(
                f">>> no additional job statistics to insert into DB for jobId: {job_id}")


    def __job_logs_to_stats(self, list_with_logs: List[Dict[str, Any]]) -> None:
        """Parses joblogs into their own statisic table, using declared supported ID's

        To parse more jobLogs define additional entrys in the attribute `supported_ids`.

        Arguments:
            list_with_logs {List[Dict[str, Any]]} -- List with all saved joblogs
        """

        # only continue with joblogs we want to save
        supported_log_iterator = filter(
            lambda log: log['messageId'] in self.__supported_ids.keys(), list_with_logs)
        sorted_log_iterator = sorted(
            supported_log_iterator, key=lambda entry: entry['logTime'])
        max_sec_timestamp = 0  # required for preventing duplicates

        for job_log in sorted_log_iterator:
            message_id = job_log['messageId']

            table_func_triple = self.__supported_ids[message_id]

            (table_name, row_dict_func, additional_fields) = table_func_triple

            if(not table_name):
                table_name = message_id
                ExceptionUtils.error_message(f"Warning: No tablename specified for message_id {message_id}. Please report to developer.")

            try:
                # Saving information from the message-params list within the job_log
                row_dict = row_dict_func(job_log['messageParams'])
                if(not row_dict):
                    # this was matched incorrectly, therefore skipped.
                    # No warning cause this will happen often.
                    continue
                # Saving additional fields from the job_log struct itself.
                if(additional_fields):
                    for (key, rename) in additional_fields:
                        row_dict[rename] = job_log[key]
            except KeyError as error:
                ExceptionUtils.exception_info(
                    error, extra_message=f"MessageID params wrong defined. Skipping message_id {message_id}")
                continue

            row_dict['messageId'] = message_id
            # Issue 9, In case where all tag values duplicate another record, including the timestamp, Influx will throw the insert
            # out as a duplicate.  In some cases, the changing of epoch timestamps from millisecond to second precision is
            # cause duplicate timestamps.  To avoid this for certain tables, add seconds to the timestamp as needed to
            # ensure uniqueness.  Only use this when some innacuracy of the timestamps is acceptable
            cur_timestamp = job_log['logTime']
            if(table_name == 'vmBackupSummary'):

                if(cur_timestamp is None):  # prevent None
                    ExceptionUtils.error_message(
                        f"Warning: logTime is None, duplicate may be purged. Log: {job_log}")

                if(isinstance(cur_timestamp, str)):  # make sure its int
                    cur_timestamp = int(cur_timestamp)

                cur_sec_timestamp = SppUtils.to_epoch_secs(cur_timestamp)
                if(cur_sec_timestamp <= max_sec_timestamp):
                    digits = (int)(cur_timestamp / cur_sec_timestamp)
                    max_sec_timestamp += 1  # increase by 1 second
                    cur_timestamp = max_sec_timestamp * digits
                else:
                    max_sec_timestamp = cur_sec_timestamp

            row_dict['time'] = cur_timestamp

            for(key, item) in row_dict.items():
                if(item in ('null', 'null(null)')):
                    row_dict[key] = None

            self.__influx_client.insert_dicts_to_buffer(table_name, [row_dict])

    def job_logs(self) -> None:
        """saves all jobLogs for the jobsessions in influx catalog.

        Make sure to call `get_all_jobs` before to aquire all jobsessions.
        In order to save them it deletes and rewrites all affected jobsession entrys.
        It automatically parses certain jobLogs into additional stats, defined by `supported_ids`.
        """

        table = self.__influx_client.database['jobs']
        # only store if there is something to store -> limited by job log rentation time.
        where_str = 'jobsLogsStored <> \'True\' and time > now() - %s' % self.__job_log_retention_time
        where_str += f' AND time > now() - {table.retention_policy.duration}'

        jobs_updated = 0
        logs_total_count = 0
        LOGGER.info("> getting joblogs for jobsessions without saved logs")
        LOGGER.info(">> requesting jobList from database")

        # Select all jobs without joblogs
        keyword = Keyword.SELECT
        query = SelectionQuery(
            keyword=keyword,
            tables=[table],
            fields=['*'],
            where_str=where_str
        )
        # send query and compute
        result = self.__influx_client.send_selection_query( # type: ignore
            query)
        result_list: List[Dict[str, Any]] = list(
            result.get_points())  # type: ignore

        rows_affected = len(result_list)

        LOGGER.info(">>> number of jobs with no joblogs stored in Influx database: {}"
                    .format(rows_affected))

        job_log_dict: Dict[int, List[Dict[str, Any]]] = {}

        # request all jobLogs from REST-API
        # if errors occur, skip single row and debug
        for row in result_list:
            job_session_id: Optional[int] = row.get('id', None)

            # if somehow id is missing: skip
            if(job_session_id is None):
                ExceptionUtils.error_message(
                    f"Error: joblogId missing for row {row}")
                continue

            if(job_session_id in job_log_dict):
                ExceptionUtils.error_message(
                    f"Error: joblogId duplicate, skipping.{job_session_id}")
                continue

            if(self.__verbose):
                LOGGER.info(
                    f">>> requested joblogs for {len(job_log_dict)} / {rows_affected} job sessions.")
            elif(len(job_log_dict) % 5 == 0):
                LOGGER.info(
                    f">>> requested joblogs for {len(job_log_dict)} / {rows_affected} job sessions.")

            # request job_session_id
            try:
                if(self.__verbose):
                    LOGGER.info(
                        f"requesting jobLogs {self.__job_log_type} for session {job_session_id}.")
                LOGGER.debug(
                    f"requesting jobLogs {self.__job_log_type} for session {job_session_id}.")

                # cant use query something like everwhere due the extra params needed
                job_log_list = self.__api_queries.get_job_log_details(
                    jobsession_id=job_session_id,
                    job_logs_type=self.__job_log_type)
            except ValueError as error:
                ExceptionUtils.exception_info(
                    error=error,
                    extra_message=f"error when api-requesting joblogs for job_session_id {job_session_id}, skipping it")
                continue

            if(self.__verbose):
                LOGGER.info(
                    f">>> Found {len(job_log_list)} logs for jobsessionId {job_session_id}")

            LOGGER.debug(
                f"Found {len(job_log_list)} logs for jobsessionId {job_session_id}")
            # default empty list if no details available -> should not happen, in for safty reasons
            # if this is none, go down to rest client and fix it. Should be empty list.
            if(job_log_list is None):
                job_log_list = []
                ExceptionUtils.error_message(
                    "A joblog_list was none, even if the type does not allow it. Please report to developers.")
            job_log_dict[job_session_id] = job_log_list

        # list to be inserted after everything is updated
        insert_list: List[Dict[str, Any]] = []

        # Query data in ranges to avoid too many requests
        # Results from first select query above
        for row in result_list:
            job_id: int = row['id']
            job_log_list: Optional[List[Dict[str, Any]]
                                   ] = job_log_dict.get(job_id, None)

            if(job_log_list is None):
                ExceptionUtils.error_message(
                    f"missing job_log_list even though it is in influxdb for jobId {job_id}. Skipping it")
                continue

            # jobLogsCount will be zero if jobLogs are deleted after X days by maintenance jobs, GUI default is 60 days
            job_logs_count = len(job_log_list)
            if(self.__verbose):
                LOGGER.info(">>> storing {} joblogs for jobsessionId: {} in Influx database".format(
                    len(job_log_list), job_id))
            LOGGER.debug(">>> storing {} joblogs for jobsessionId: {} in Influx database".format(
                len(job_log_list), job_id))

            for job_log in job_log_list:
                # rename log keys and add additional information
                job_log["jobId"] = row.get("jobId", None)
                job_log["jobName"] = row.get("jobName", None)
                job_log["jobExecutionTime"] = row.get("start", None)
                job_log["jobLogId"] = job_log.pop("id")
                job_log["jobSessionId"] = job_log.pop("jobsessionId")

            # compute other stats out of jobList
            try:
                self.__job_logs_to_stats(job_log_list)
            except ValueError as error:
                ExceptionUtils.exception_info(
                    error, extra_message=f"Failed to compute stats out of job logs, skipping for jobsessionId {job_id}")

            for job_log in job_log_list:
                # dump message params to allow saving as string
                job_log["messageParams"] = json.dumps(job_log["messageParams"])

            # if list is empty due beeing erased etc it will simply return and do nothing
            self.__influx_client.insert_dicts_to_buffer(
                list_with_dicts=job_log_list, table_name="jobLogs")

            jobs_updated += 1
            logs_total_count += job_logs_count
            # update job table and set jobsLogsStored = True, jobLogsCount = len(jobLogDetails)
            update_fields = {
                "jobLogsCount": job_logs_count,
                "jobsLogsStored": True
            }
            # copy dict to allow update without errors
            mydict = dict(row.items())
            # update fields
            for(key, value) in update_fields.items():
                mydict[key] = value
            insert_list.append(mydict)

        # Delete data to allow reinsert with different tags
        delete_query = SelectionQuery(
            keyword=Keyword.DELETE,
            tables=[table],
            where_str=where_str
        )

        # now send remove query to prevent data loss
        self.__influx_client.send_selection_query(delete_query) # type: ignore

        # Insert data after everything is completed
        self.__influx_client.insert_dicts_to_buffer(table.name, insert_list)

        LOGGER.info(">>> inserted a total of {} logs".format(logs_total_count))
